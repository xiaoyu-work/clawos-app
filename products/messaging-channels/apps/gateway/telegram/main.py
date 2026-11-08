"""Telegram outbound client and Root-owned channel lifecycle presentation."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse

from gateway._shared import channels, gateway_memory, safe_egress, safe_subprocess

PLATFORM = "telegram"
TG_API_BASE = "https://api.telegram.org"
TG_API_HOST = "api.telegram.org"
TG_MESSAGE_LIMIT = 4096


def _cos_bin():
    return os.environ.get("COS_BIN", "cos")


def _load_token():
    env_token = os.environ.get("COS_TELEGRAM_TOKEN")
    if env_token:
        return env_token.strip()
    token, error = safe_subprocess.safe_credential_load("telegram_bot_token", timeout=10.0, cos_bin=_cos_bin())
    if token is None:
        raise RuntimeError(error or "telegram_bot_token not in credential store; run `cos credential store telegram_bot_token <token>` first")
    return token


def _api_call(token, method, params, timeout):
    body = urllib.parse.urlencode(params).encode("utf-8")
    _, _, raw = safe_egress.safe_urlopen(
        "POST", f"{TG_API_BASE}/bot{token}/{method}",
        headers={"Content-Type": "application/x-www-form-urlencoded"}, body=body, timeout=timeout, verb_id="net.dial",
    )
    payload = json.loads(raw.decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(f"telegram api error: {payload.get('description', 'unknown')}")
    return payload


def _truncate(text):
    return text if len(text) <= TG_MESSAGE_LIMIT else text[:TG_MESSAGE_LIMIT - 1] + "\u2026"


def _send(args):
    if isinstance(args, dict):
        chat_id, text = args.get("chat_id", ""), args.get("text", "")
        if isinstance(text, list):
            text = " ".join(str(part) for part in text)
    elif isinstance(args, list) and len(args) >= 2:
        chat_id, text = args[0], " ".join(str(part) for part in args[1:])
    else:
        return {"ok": False, "error": "usage: send <chat_id> <text>"}
    try:
        _api_call(_load_token(), "sendMessage", {"chat_id": chat_id, "text": _truncate(text)}, timeout=15)
    except (urllib.error.URLError, RuntimeError, safe_egress.EgressBlocked) as error:
        return {"ok": False, "error": str(error)}
    return {"ok": True, "platform": PLATFORM, "sent_to": chat_id, "len": len(text)}


def run(command, args):
    if command in {"start", "stop", "status", "reply"}:
        return channels.run(PLATFORM, command, args)
    from canonical_argv import normalize_canonical_argv
    if isinstance(args, list):
        args = normalize_canonical_argv(args)
    if command == "send":
        result = _send(args)
        chat_id = str(args.get("chat_id", "")) if isinstance(args, dict) else (str(args[0]) if args else "")
        text = args.get("text", "") if isinstance(args, dict) else args[1:]
        text = " ".join(str(part) for part in text) if isinstance(text, list) else str(text)
        gateway_memory.remember_send(PLATFORM, result, channel_id=chat_id, text=text)
        return result
    return {"error": f"unknown command: {command}"}


if __name__ == "__main__":
    cmd = os.environ.get("COS_COMMAND") or (sys.argv[1] if len(sys.argv) > 1 else "")
    raw_args = os.environ.get("COS_ARGS_JSON")
    print(json.dumps(run(cmd, json.loads(raw_args) if raw_args else sys.argv[2:])))
