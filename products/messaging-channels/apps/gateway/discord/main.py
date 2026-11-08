"""Discord outbound client and presentation for the Root-owned channel service.

App-local legacy preferences are retained, but never authorize inbound messages.
Use the protected OS channel configuration and an existing Activity trigger.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import time
import urllib.error
from typing import Any

from gateway._shared import atomic, channels, gateway_memory, safe_egress, safe_subprocess

try:
    from cos_runtime import policy as _cos_policy
except ImportError:
    _cos_policy = None

_POLICY_ERRORS = (_cos_policy.PolicyError,) if _cos_policy is not None else ()
PLATFORM = "discord"
VERSION = "0.3.0"
DISCORD_API = "https://discord.com/api/v10"
USER_AGENT = "DiscordBot (https://github.com/xiaoyu-work/claw-os, 0.3.0)"
MAX_MESSAGE_LEN = 2000
DEFAULT_RPM = 5
ENV_TOKEN = "COS_DISCORD_TOKEN"
ENV_ALLOWED_USERS = "COS_DISCORD_ALLOWED_USERS"
ENV_ALLOWED_GUILDS = "COS_DISCORD_ALLOWED_GUILDS"
ENV_ALLOWED_CHANNELS = "COS_DISCORD_ALLOWED_CHANNELS"
ENV_REQUIRE_MENTION = "COS_DISCORD_REQUIRE_MENTION"
ENV_RPM = "COS_DISCORD_RPM"
_ID_RE = re.compile(r"^\d{1,20}$")


class DiscordApiError(Exception):
    """Discord REST API returned an error response."""


def _state_dir() -> str:
    base = os.environ.get("COS_DATA_DIR")
    if not base:
        base = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "cos") if sys.platform == "win32" else "/var/lib/cos"
    path = os.path.join(base, "apps", "gateway-discord")
    os.makedirs(path, exist_ok=True)
    return path


def _config_path() -> str:
    return os.path.join(_state_dir(), "config.json")


def _read_stored_config() -> dict[str, Any]:
    try:
        with open(_config_path(), "r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Discord config JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise ValueError("Discord config must be a JSON object")
    return config


def _parse_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{field} must be true or false")


def _parse_ids(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        raise ValueError(f"{field} must be a comma-separated string or list")
    out = []
    for item in values:
        item = str(item).strip()
        if not item:
            continue
        if item != "*" and not _ID_RE.fullmatch(item):
            raise ValueError(f"{field} contains an invalid Discord id: {item!r}")
        if item not in out:
            out.append(item)
    return out


def _validate_config(raw: dict[str, Any]) -> dict[str, Any]:
    try:
        rpm = int(raw.get("requests_per_minute", DEFAULT_RPM))
    except (TypeError, ValueError):
        raise ValueError("requests_per_minute must be an integer") from None
    if not 1 <= rpm <= 60:
        raise ValueError("requests_per_minute must be between 1 and 60")
    return {
        "allowed_users": _parse_ids(raw.get("allowed_users"), "allowed_users"),
        "allowed_guilds": _parse_ids(raw.get("allowed_guilds"), "allowed_guilds"),
        "allowed_channels": _parse_ids(raw.get("allowed_channels"), "allowed_channels"),
        "require_mention": _parse_bool(raw.get("require_mention", True), "require_mention"),
        "requests_per_minute": rpm,
    }


def _effective_config() -> dict[str, Any]:
    raw = _read_stored_config()
    for env_name, key in {
        ENV_ALLOWED_USERS: "allowed_users", ENV_ALLOWED_GUILDS: "allowed_guilds",
        ENV_ALLOWED_CHANNELS: "allowed_channels", ENV_REQUIRE_MENTION: "require_mention",
        ENV_RPM: "requests_per_minute",
    }.items():
        if env_name in os.environ:
            raw[key] = os.environ[env_name]
    return _validate_config(raw)


def _configure(args: Any) -> dict[str, Any]:
    aliases = {
        "users": "allowed_users", "allowed_users": "allowed_users",
        "guilds": "allowed_guilds", "allowed_guilds": "allowed_guilds",
        "channels": "allowed_channels", "allowed_channels": "allowed_channels",
        "require_mention": "require_mention",
        "rpm": "requests_per_minute", "requests_per_minute": "requests_per_minute",
    }
    updates = {}
    if isinstance(args, dict):
        if set(args) == {"settings"}:
            settings = args["settings"]
            return _configure(settings if isinstance(settings, list) else [settings])
        for key, value in args.items():
            canonical = aliases.get(str(key))
            if canonical is None:
                return {"ok": False, "error": f"unknown setting: {key}"}
            updates[canonical] = value
    elif isinstance(args, list):
        try:
            tokens = shlex.split(" ".join(str(arg) for arg in args))
        except ValueError as exc:
            return {"ok": False, "error": f"invalid settings: {exc}"}
        for token in tokens:
            if "=" not in token:
                return {"ok": False, "error": f"expected key=value setting, got {token!r}"}
            key, value = token.split("=", 1)
            canonical = aliases.get(key.strip())
            if canonical is None:
                return {"ok": False, "error": f"unknown setting: {key}"}
            updates[canonical] = value
    else:
        return {"ok": False, "error": "settings must be key=value text or an object"}
    try:
        stored = _read_stored_config()
        stored.update(updates)
        config = _validate_config(stored)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if not config["allowed_users"]:
        return {"ok": False, "error": "allowed_users is required; refusing an open inbound gateway"}
    atomic.atomic_write_json(_config_path(), config)
    return {
        "ok": True, "platform": PLATFORM, "configured": config,
        "owner_admission": False,
        "note": "Legacy preferences only. Configure authenticated ingress with cos channels configure discord.",
    }


def _cos_bin() -> str:
    return os.environ.get("COS_BIN", "cos")


def _load_token() -> str:
    env_token = os.environ.get(ENV_TOKEN)
    if env_token:
        return env_token.strip()
    token, error = safe_subprocess.safe_credential_load("discord_bot_token", timeout=10.0, cos_bin=_cos_bin())
    if token is None:
        raise RuntimeError(error or "discord_bot_token is not configured; run `cos credential store discord_bot_token <token>`")
    return token


def _api_call(token, method, path, payload=None, *, timeout=15.0, retry_rate_limit=True):
    body = None
    headers = {"Authorization": f"Bot {token}", "User-Agent": USER_AGENT}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        _, _, raw = safe_egress.safe_urlopen(
            method, f"{DISCORD_API}{path}", headers=headers, body=body, timeout=timeout, verb_id="net.dial",
        )
    except urllib.error.HTTPError as exc:
        raw_error = exc.read().decode("utf-8", errors="replace")
        if exc.code == 429 and retry_rate_limit:
            try:
                retry_after = float(json.loads(raw_error).get("retry_after", 1))
            except (json.JSONDecodeError, TypeError, ValueError):
                retry_after = 1.0
            time.sleep(min(max(retry_after, 0.1), 10.0))
            return _api_call(token, method, path, payload, timeout=timeout, retry_rate_limit=False)
        try:
            detail = json.loads(raw_error).get("message", "unknown error")
        except json.JSONDecodeError:
            detail = raw_error[:300] or str(exc.reason)
        raise DiscordApiError(f"Discord HTTP {exc.code}: {detail}") from exc
    if not raw:
        return {}
    try:
        response = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise DiscordApiError("Discord returned a non-JSON response") from exc
    if not isinstance(response, dict):
        raise DiscordApiError("Discord returned an invalid JSON response")
    return response


def _validate_snowflake(value, field):
    value = str(value or "").strip()
    if not _ID_RE.fullmatch(value):
        raise ValueError(f"{field} must be a Discord snowflake id")
    return value


def _split_message(text):
    text = str(text or "").strip()
    if not text:
        return ["[agent returned an empty response]"]
    chunks = []
    while len(text) > MAX_MESSAGE_LEN:
        cut = text.rfind("\n", 0, MAX_MESSAGE_LEN + 1)
        if cut < MAX_MESSAGE_LEN // 2:
            cut = text.rfind(" ", 0, MAX_MESSAGE_LEN + 1)
        if cut < MAX_MESSAGE_LEN // 2:
            cut = MAX_MESSAGE_LEN
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks


def _send_messages(token, channel_id, text, *, reply_to=None):
    channel_id = _validate_snowflake(channel_id, "channel_id")
    reply_id = _validate_snowflake(reply_to, "reply_to") if reply_to is not None else None
    message_ids = []
    for index, chunk in enumerate(_split_message(text)):
        payload = {"content": chunk, "allowed_mentions": {"parse": [], "replied_user": False}}
        if index == 0 and reply_id is not None:
            payload["message_reference"] = {"message_id": reply_id, "channel_id": channel_id, "fail_if_not_exists": False}
        response = _api_call(token, "POST", f"/channels/{channel_id}/messages", payload)
        if isinstance(response.get("id"), str):
            message_ids.append(response["id"])
    return {
        "ok": True, "platform": PLATFORM, "channel_id": channel_id,
        "message_id": message_ids[0] if message_ids else None,
        "message_ids": message_ids, "chunks": len(message_ids),
    }


def _send(args):
    if isinstance(args, dict):
        channel_id, text = args.get("channel_id"), args.get("text")
        if isinstance(text, list):
            text = " ".join(str(part) for part in text)
    elif isinstance(args, list):
        channel_id = args[0] if args else None
        text = " ".join(str(value) for value in args[1:]) if len(args) > 1 else None
    else:
        return {"ok": False, "platform": PLATFORM, "error": "invalid args"}
    if not text or not str(text).strip():
        return {"ok": False, "platform": PLATFORM, "error": "text is required"}
    try:
        return _send_messages(_load_token(), channel_id, str(text))
    except (RuntimeError, DiscordApiError, safe_egress.EgressBlocked, urllib.error.URLError, ValueError) as exc:
        return {"ok": False, "platform": PLATFORM, "error": str(exc)}
    except _POLICY_ERRORS as exc:
        return {"ok": False, "platform": PLATFORM, "error": "Discord send permission denied", "denial": getattr(exc, "denial", None)}


def run(command, args):
    if command in {"start", "stop", "status", "reply"}:
        return channels.run(PLATFORM, command, args)
    from canonical_argv import normalize_canonical_argv
    if isinstance(args, list):
        args = normalize_canonical_argv(args)
    if command == "configure":
        return _configure(args)
    if command == "send":
        result = _send(args)
        channel_id = str(args.get("channel_id") or "") if isinstance(args, dict) else (str(args[0]) if args else "")
        text = args.get("text", "") if isinstance(args, dict) else args[1:]
        text = " ".join(str(part) for part in text) if isinstance(text, list) else str(text)
        gateway_memory.remember_send(PLATFORM, result, channel_id=channel_id, text=text)
        return result
    return {"ok": False, "error": f"unknown command: {command}"}


if __name__ == "__main__":
    cmd = os.environ.get("COS_COMMAND") or (sys.argv[1] if len(sys.argv) > 1 else "")
    raw_args = os.environ.get("COS_ARGS_JSON")
    print(json.dumps(run(cmd, json.loads(raw_args) if raw_args else sys.argv[2:])))
