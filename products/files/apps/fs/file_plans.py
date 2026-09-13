"""Bounded App-owned file plans; applying always requires fresh path authority."""

from __future__ import annotations

import contextlib
import datetime
import difflib
import fcntl
import hashlib
import json
import os
import stat
import time
import uuid

from _shared.atomic import _fsync_dir, atomic_write_json
from claw_os_sdk.objects import format_reference
from cos_runtime import file_changes, policy, snapshot

MAX_TEXT_BYTES = 65536
MAX_PLAN_BYTES = 1024 * 1024
MAX_DIFF_BYTES = 65536
MAX_PLANS = 64
STORE_SCOPE = "fs-change-plans"
STATES = {"draft", "applying", "applied", "conflicted", "indeterminate", "expired"}
STATE_KEYS = {"sha256", "size", "device", "inode", "mode", "modified_ns", "changed_ns"}
RECORD_KEYS = {
    "schema", "kind", "plan_id", "path", "before", "before_text", "after_text",
    "created_at", "expires_at", "review", "state", "snapshot", "applied_at",
    "changed", "diagnostic",
}


class PlanError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _hash(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _now():
    return int(time.time())


def _timestamp(seconds):
    return datetime.datetime.fromtimestamp(
        seconds, datetime.timezone.utc
    ).isoformat().replace("+00:00", "Z")


def _seconds(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PlanError("plan_invalid", "plan timestamps must be UTC")
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return int(parsed.timestamp())
    except (ValueError, OverflowError) as error:
        raise PlanError("plan_invalid", "invalid plan timestamp") from error


def _identifier(value):
    try:
        parsed = uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as error:
        raise PlanError("invalid_args", "plan ID must be a canonical UUID") from error
    if str(parsed) != value:
        raise PlanError("invalid_args", "plan ID must be a canonical UUID")
    return value


def _digest(value):
    return isinstance(value, str) and len(value) == 71 and value.startswith(
        "sha256:"
    ) and all(character in "0123456789abcdef" for character in value[7:])


def _path(value):
    try:
        file_changes.validate_path(value)
        path = os.path.realpath(value)
        file_changes.validate_path(path)
    except file_changes.FileChangeError as error:
        raise PlanError("invalid_args", str(error)) from error
    if len(path.encode("utf-8")) > 1024:
        raise PlanError(
            "unsupported_file", "file plan paths must fit the 1024-byte object identity limit"
        )
    return path


def _text_bytes(value):
    if not isinstance(value, str):
        raise PlanError("invalid_args", "file plan content must be text")
    try:
        data = value.encode("utf-8")
    except UnicodeError as error:
        raise PlanError("invalid_args", "file plan content must be valid UTF-8") from error
    if len(data) > MAX_TEXT_BYTES or b"\0" in data:
        raise PlanError(
            "unsupported_file", "file plans support UTF-8 text without NUL, up to 64 KiB"
        )
    return data


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise PlanError(
            "invalid_args", f"{name} must be an integer between {minimum} and {maximum}"
        )


def _identity(metadata):
    return {
        "size": metadata.st_size,
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "mode": metadata.st_mode,
        "modified_ns": metadata.st_mtime_ns,
        "changed_ns": metadata.st_ctime_ns,
    }


def _read_target(path):
    # An exact read mount need not expose an absent target's parent directory.
    # The broker checks host absence and parent existence before creating it.
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None, ""
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise PlanError("unsupported_file", "file plans require a regular single-link target")
        if before.st_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
            raise PlanError("unsupported_file", "special permission bits are not supported")
        if before.st_size > MAX_TEXT_BYTES:
            raise PlanError("unsupported_file", "target exceeds the 64 KiB file plan limit")
        if os.listxattr(fd):
            raise PlanError("unsupported_file", "file plans do not discard extended attributes")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(MAX_TEXT_BYTES + 1)
            after = os.fstat(fd)
    finally:
        os.close(fd)
    if _identity(before) != _identity(after) or len(data) != after.st_size:
        raise PlanError("plan_conflict", "target changed while it was being read")
    try:
        text = data.decode("utf-8")
    except UnicodeError as error:
        raise PlanError("unsupported_file", "target is not UTF-8 text") from error
    _text_bytes(text)
    return dict(_identity(after), sha256=_hash(data)), text


def _private_directory(path, create=False):
    if create:
        try:
            os.mkdir(path, 0o700)
        except FileExistsError:
            pass
    metadata = os.stat(path, follow_symlinks=False)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid():
        raise PlanError("plan_storage", "plan directory must be a real owner-owned directory")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise PlanError("plan_storage", "plan directory must be private (0700)")
    if create:
        # Sync the ancestors too: a synced record alone cannot persist a new bucket.
        _fsync_dir(os.path.dirname(path), strict=True)
    return path


def _bucket(path, create=False):
    root = os.environ.get("COS_DATA_DIR")
    if not root or not os.path.isabs(root):
        raise PlanError("plan_storage", "App data directory is not configured")
    _private_directory(root)
    plans = _private_directory(os.path.join(root, "file-change-plans"), create)
    name = hashlib.sha256(path.encode("utf-8")).hexdigest()
    return _private_directory(os.path.join(plans, name), create)


def _private_file(fd):
    metadata = os.fstat(fd)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise PlanError("plan_storage", "plan storage must use regular single-link files")
    if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise PlanError("plan_storage", "plan storage must be private and owner-owned")
    return metadata


@contextlib.contextmanager
def _locked(path, *, create=False, exclusive=False):
    directory = _bucket(path, create)
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
    if create:
        flags |= os.O_CREAT
    fd = os.open(os.path.join(directory, "bucket.lock"), flags, 0o600)
    try:
        _private_file(fd)
        fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield directory
    finally:
        os.close(fd)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PlanError("plan_invalid", "duplicate field in stored plan")
        result[key] = value
    return result


def _review(plan):
    bound = {
        "schema": 1,
        "plan_id": plan["plan_id"],
        "path": plan["path"],
        "before": plan["before"],
        "after_sha256": _hash(_text_bytes(plan["after_text"])),
        "created_at": plan["created_at"],
        "expires_at": plan["expires_at"],
    }
    return _hash(json.dumps(
        bound, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8"))


def _validate(plan, path, plan_id):
    if not isinstance(plan, dict) or set(plan) != RECORD_KEYS:
        raise PlanError("plan_invalid", "stored plan has an invalid shape")
    if (
        type(plan["schema"]) is not int
        or plan["schema"] != 1
        or plan["kind"] != "file_change_plan_record"
    ):
        raise PlanError("plan_invalid", "unsupported stored plan format")
    if (
        plan["plan_id"] != plan_id or plan["path"] != path
        or not isinstance(plan["state"], str) or plan["state"] not in STATES
    ):
        raise PlanError("plan_invalid", "stored plan identity or state does not match")
    before = _text_bytes(plan["before_text"])
    _text_bytes(plan["after_text"])
    state = plan["before"]
    if state is None:
        if before:
            raise PlanError("plan_invalid", "absent baseline cannot contain bytes")
    elif not isinstance(state, dict) or set(state) != STATE_KEYS:
        raise PlanError("plan_invalid", "invalid baseline fingerprint")
    else:
        for key in STATE_KEYS - {"sha256"}:
            if type(state[key]) is not int:
                raise PlanError("plan_invalid", "baseline metadata must contain integers")
        if any(state[key] < 0 for key in ("size", "device", "inode", "mode")):
            raise PlanError("plan_invalid", "baseline metadata is outside its domain")
        if (
            any(state[key] > (1 << 64) - 1 for key in ("device", "inode"))
            or state["mode"] > (1 << 32) - 1
        ):
            raise PlanError("plan_invalid", "baseline identity is outside its domain")
        if any(
            not -(1 << 63) <= state[key] < (1 << 63)
            for key in ("modified_ns", "changed_ns")
        ):
            raise PlanError("plan_invalid", "baseline timestamps are outside their domain")
        if (
            not stat.S_ISREG(state["mode"])
            or state["size"] != len(before) or state["sha256"] != _hash(before)
        ):
            raise PlanError("plan_invalid", "baseline content does not match its fingerprint")
    duration = _seconds(plan["expires_at"]) - _seconds(plan["created_at"])
    if not 60 <= duration <= 86400:
        raise PlanError("plan_invalid", "plan lifetime must be between one minute and one day")
    if plan["review"] != _review(plan):
        raise PlanError("plan_invalid", "stored proposal does not match its review fingerprint")
    for field in ("snapshot", "applied_at", "diagnostic"):
        value = plan[field]
        if value is not None and (
            not isinstance(value, str) or len(value.encode("utf-8")) > 4096
        ):
            raise PlanError("plan_invalid", "invalid plan lifecycle metadata")
    if plan["changed"] is not None and type(plan["changed"]) is not bool:
        raise PlanError("plan_invalid", "invalid change outcome")
    if plan["state"] == "applied":
        _seconds(plan["applied_at"])
        if type(plan["changed"]) is not bool:
            raise PlanError("plan_invalid", "applied plan is missing its reported change outcome")
    elif plan["applied_at"] is not None or plan["changed"] is not None:
        raise PlanError("plan_invalid", "unfinished plan cannot claim a completed apply outcome")


def _load(directory, path, plan_id):
    filename = os.path.join(directory, _identifier(plan_id) + ".json")
    fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        metadata = _private_file(fd)
        if metadata.st_size > MAX_PLAN_BYTES:
            raise PlanError("plan_invalid", "stored plan exceeds its size bound")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_PLAN_BYTES + 1)
    finally:
        os.close(fd)
    if len(raw) > MAX_PLAN_BYTES:
        raise PlanError("plan_invalid", "stored plan exceeds its size bound")
    try:
        plan = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise PlanError("plan_invalid", "stored plan is not valid JSON") from error
    _validate(plan, path, plan_id)
    return plan


def _save(directory, plan):
    _validate(plan, plan["path"], plan["plan_id"])
    atomic_write_json(
        os.path.join(directory, plan["plan_id"] + ".json"), plan, mode=0o600, strict=True
    )


def _ids(directory):
    ids = []
    with os.scandir(directory) as entries:
        for entry in entries:
            if entry.name == "bucket.lock":
                continue
            if not entry.name.endswith(".json"):
                raise PlanError("plan_storage", "unexpected entry in the plan directory")
            ids.append(_identifier(entry.name[:-5]))
            if len(ids) > MAX_PLANS:
                raise PlanError("plan_limit", "stored plan count exceeds its bound")
    return ids


def _public(plan):
    before = _text_bytes(plan["before_text"])
    after = _text_bytes(plan["after_text"])
    lines = difflib.unified_diff(
        plan["before_text"].splitlines(keepends=True),
        plan["after_text"].splitlines(keepends=True),
        fromfile=plan["path"] + " (before)", tofile=plan["path"] + " (proposed)",
    )
    diff = "".join(
        line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
        for line in lines
    )
    encoded = diff.encode("utf-8")
    truncated = len(encoded) > MAX_DIFF_BYTES
    if truncated:
        diff = encoded[:MAX_DIFF_BYTES].decode("utf-8", errors="ignore")
    state = plan["state"]
    if state == "draft" and _now() >= _seconds(plan["expires_at"]):
        state = "expired"
    warnings = [
        "App-reported file plan, not authorization or OS-confirmed effects.",
        "Apply requires an explicit path, review fingerprint, confirmation, and fresh file permissions.",
        "Cooperative calls are serialized, but uncooperative external writers can race after the final check.",
        "Recovery remains unknown; a snapshot reference is not proof that an OS rollback is available.",
    ]
    if state in ("applying", "indeterminate"):
        warnings.append("The apply outcome is unknown; automatic replay is refused.")
    return {
        "schema": 1, "kind": "file_change_plan", "plan_id": plan["plan_id"],
        "path": plan["path"], "state": state,
        "before_exists": plan["before"] is not None,
        "before_sha256": None if plan["before"] is None else plan["before"]["sha256"],
        "after_sha256": _hash(after), "before_bytes": len(before), "after_bytes": len(after),
        "would_change": plan["before"] is None or before != after,
        "review": plan["review"],
        "reference": format_reference({
            "app_id": "fs", "object_type": "change-plan", "object_id": plan["path"],
            "revision": plan["plan_id"],
        }),
        "diff": diff, "diff_truncated": truncated,
        "created_at": plan["created_at"], "expires_at": plan["expires_at"],
        "warnings": warnings, "snapshot": plan["snapshot"], "applied_at": plan["applied_at"],
        "changed": plan["changed"], "diagnostic": plan["diagnostic"],
    }


def plan_write(path: str, content: str, ttl_seconds: int = 3600) -> dict:
    path = _path(path)
    _text_bytes(content)
    _integer(ttl_seconds, "ttl_seconds", 60, 86400)
    policy.require("fs.read", path=path)
    policy.require("data.db.write", name=STORE_SCOPE)
    with _locked(path, create=True, exclusive=True) as directory:
        if len(_ids(directory)) >= MAX_PLANS:
            raise PlanError(
                "plan_limit", "plan limit reached; prune consumed or expired plans explicitly"
            )
        before, before_text = _read_target(path)
        now = _now()
        plan = {
            "schema": 1, "kind": "file_change_plan_record",
            "plan_id": str(uuid.uuid4()), "path": path, "before": before,
            "before_text": before_text, "after_text": content,
            "created_at": _timestamp(now), "expires_at": _timestamp(now + ttl_seconds),
            "review": "", "state": "draft", "snapshot": None,
            "applied_at": None, "changed": None, "diagnostic": None,
        }
        plan["review"] = _review(plan)
        _save(directory, plan)
        return _public(plan)


def plan_show(path: str, plan: str | None = None) -> dict:
    path = _path(path)
    plan_id = _identifier(plan) if plan is not None else None
    policy.require("fs.read", path=path)
    policy.require("data.db.read", name=STORE_SCOPE)
    with _locked(path) as directory:
        if plan_id is None:
            plans = [_load(directory, path, candidate) for candidate in _ids(directory)]
            if not plans:
                raise PlanError("plan_not_found", "no file plans exist for this path")
            record = max(plans, key=lambda item: (item["created_at"], item["plan_id"]))
        else:
            record = _load(directory, path, plan_id)
        return _public(record)


def _conflict(directory, plan, diagnostic):
    plan["state"] = "conflicted"
    plan["diagnostic"] = diagnostic + " No target write was attempted."
    _save(directory, plan)
    raise PlanError("plan_conflict", plan["diagnostic"])


def plan_apply(
    path: str, plan: str, review: str, confirm: bool, *, session_id: str | None
) -> dict:
    path = _path(path)
    if confirm is not True:
        raise PlanError("invalid_args", "plan_apply requires explicit confirmation")
    plan_id = _identifier(plan)
    if not _digest(review):
        raise PlanError("invalid_args", "plan_apply requires the exact review fingerprint")
    if not isinstance(session_id, str) or not session_id:
        raise PlanError("plan_context", "plan_apply requires an authenticated calling session")
    policy.require("fs.read", path=path)
    policy.require("fs.write", path=path)
    policy.require("data.db.read", name=STORE_SCOPE)
    policy.require("data.db.write", name=STORE_SCOPE)
    with _locked(path, exclusive=True) as directory:
        record = _load(directory, path, plan_id)
        if record["state"] != "draft":
            code = (
                "plan_indeterminate"
                if record["state"] in ("applying", "indeterminate") else "plan_consumed"
            )
            raise PlanError(
                code, "this plan cannot be replayed; inspect its state and create a fresh plan"
            )
        if _now() >= _seconds(record["expires_at"]):
            raise PlanError("plan_expired", "file plan has expired")
        if review != record["review"]:
            _conflict(directory, record, "Proposal changed after review.")
        try:
            current, _ = _read_target(path)
        except PlanError as error:
            _conflict(directory, record, str(error))
        if current != record["before"]:
            _conflict(directory, record, "Target changed since this plan was prepared.")
        record["state"] = "applying"
        _save(directory, record)
        try:
            record["snapshot"] = snapshot.snapshot(path, "write", session_id=session_id)
            content = _text_bytes(record["after_text"])
            result = file_changes.replace_file(
                path, record["before"], content, session_id=session_id
            )
            if (
                not isinstance(result, dict)
                or result.get("path") != path or result.get("sha256") != _hash(content)
                or type(result.get("bytes")) is not int or result["bytes"] != len(content)
                or type(result.get("changed")) is not bool
                or (
                    not result["changed"]
                    and (record["before"] is None or record["before_text"] != record["after_text"])
                )
            ):
                raise PlanError("plan_indeterminate", "file broker returned an inconsistent result")
            record["state"] = "applied"
            record["applied_at"] = _timestamp(_now())
            record["changed"] = result["changed"]
            _save(directory, record)
        except (OSError, RuntimeError, file_changes.FileChangeError, PlanError) as error:
            record["state"] = "indeterminate"
            record["applied_at"] = None
            record["changed"] = None
            detail = str(error).encode("utf-8", errors="backslashreplace")
            reason = detail[:2048].decode("utf-8", errors="ignore")
            if len(detail) > 2048:
                reason += " [truncated]"
            record["diagnostic"] = (
                "Apply may have taken effect; automatic replay is disabled. " + reason
            )
            try:
                _save(directory, record)
            except OSError as storage_error:
                raise PlanError(
                    "plan_indeterminate",
                    "Apply outcome and final plan persistence are uncertain; preserve the plan and inspect the target",
                ) from storage_error
            raise PlanError("plan_indeterminate", record["diagnostic"]) from error
        return _public(record)


def plan_prune(path: str, confirm: bool, keep: int = 10) -> dict:
    path = _path(path)
    if confirm is not True:
        raise PlanError("invalid_args", "plan_prune requires explicit confirmation")
    _integer(keep, "keep", 0, MAX_PLANS)
    policy.require("fs.read", path=path)
    policy.require("data.db.read", name=STORE_SCOPE)
    policy.require("data.db.write", name=STORE_SCOPE)
    with _locked(path, exclusive=True) as directory:
        plans = [_load(directory, path, plan_id) for plan_id in _ids(directory)]
        retired = sorted(
            (
                plan for plan in plans
                if plan["state"] in ("applied", "conflicted", "expired")
                or (plan["state"] == "draft" and _now() >= _seconds(plan["expires_at"]))
            ),
            key=lambda plan: (plan["created_at"], plan["plan_id"]), reverse=True,
        )
        removed = []
        for plan in retired[keep:]:
            os.unlink(os.path.join(directory, plan["plan_id"] + ".json"))
            removed.append(plan["plan_id"])
        if removed:
            _fsync_dir(directory, strict=True)
        return {"removed": removed, "kept": len(plans) - len(removed), "target_changed": False}
