"""Agent Mail operations over the owner's existing Thunderbird accounts."""

import argparse
import base64
import fcntl
import hashlib
import json
import os
import stat
import time
import uuid

from _shared.atomic import atomic_write_json, _fsync_dir
from _shared.paths import safe_realpath
from claw_os_sdk import ai, events, kernel
from claw_os_sdk.mcp import current_context
from claw_os_sdk.objects import format_reference
from cos_runtime import memory, policy


MAX_ATTACHMENT_BYTES = 16 * 1024 * 1024
MAX_BODY_BYTES = 256 * 1024


def _account(value):
    profile, separator, native = value.partition(":")
    if (
        not separator or str(uuid.UUID(profile)) != profile
        or not 1 <= len(native) <= 64
        or not all(character.isascii() and (character.isalnum() or character in "_-") for character in native)
    ):
        raise ValueError("use a Thunderbird account id returned by email.accounts")
    return value


def _message_account(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 8192:
        raise ValueError("invalid Thunderbird message reference")
    raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    parts = json.loads(raw)
    if (
        not isinstance(parts, list) or len(parts) != 3
        or any(not isinstance(part, str) or not 1 <= len(part) <= 4096 for part in parts)
    ):
        raise ValueError("invalid Thunderbird message reference")
    return _account(parts[0])


def _reference(kind, value):
    return format_reference({
        "app_id": "email", "object_type": kind, "object_id": value,
    })


def _context():
    try:
        return current_context()
    except RuntimeError:
        return None


def _mail(action, account=None, **arguments):
    context = _context()
    deadline = time.time_ns() // 1_000_000 + 55_000
    if context is not None and context.deadline_unix_ms is not None:
        deadline = min(deadline, context.deadline_unix_ms)
    request = {
        "action": action,
        "args": {key: value for key, value in arguments.items() if value is not None},
        "deadline_unix_ms": deadline,
    }
    if account is not None:
        request["account"] = account
    return kernel.call_json_with_stdin_binary(
        os.environ.get("CLAW_COS_BIN", "/usr/local/bin/cos"),
        ["__mail", "request", "--request-stdin"],
        json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8"),
        deadline_unix_ms=deadline,
        check_cancelled=context.raise_if_cancelled if context is not None else None,
    )


def _parser(command):
    return argparse.ArgumentParser(prog=f"email {command}", add_help=False)


def _account_parser(command):
    parser = _parser(command)
    parser.add_argument("--account", required=True, type=_account)
    return parser


def _headers(options):
    for value in (options.to, options.subject, options.cc or ""):
        if any(character in value for character in "\r\n\0") or len(value.encode("utf-8")) > 4096:
            raise ValueError("mail recipient and subject headers must be bounded and contain no newlines")
    if not options.to.strip():
        raise ValueError("mail recipient list cannot be empty")
    if "\0" in options.body or len(options.body.encode("utf-8")) > MAX_BODY_BYTES:
        raise ValueError("mail body exceeds the Thunderbird request limit")


def _message(result):
    if "error" not in result and result.get("id"):
        result = {**result, "object": _reference("thunderbird-message", result["id"])}
    if "messages" in result:
        result = {**result, "messages": [
            {**item, "object": _reference("thunderbird-message", item["id"])}
            for item in result["messages"]
        ]}
    return result


def cmd_accounts(args):
    _parser("accounts").parse_args(args)
    policy.require("mail.accounts", wild=True)
    return _mail("accounts")


def cmd_folders(args):
    options = _account_parser("folders").parse_args(args)
    policy.require("mail.read", name=options.account)
    return _mail("folders", options.account)


def cmd_list(args):
    parser = _account_parser("list")
    parser.add_argument("--folder")
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--unread", action="store_true")
    options = parser.parse_args(args)
    if not 1 <= options.max_results <= 100:
        raise ValueError("max-results must be between 1 and 100")
    policy.require("mail.read", name=options.account)
    return _message(_mail(
        "list", options.account, folder=options.folder,
        max_results=options.max_results, unread=options.unread,
    ))


def cmd_search(args):
    parser = _account_parser("search")
    parser.add_argument("--query", required=True)
    parser.add_argument("--folder")
    parser.add_argument("--max-results", type=int, default=10)
    options = parser.parse_args(args)
    if not options.query.strip() or len(options.query.encode("utf-8")) > 4096:
        raise ValueError("query must be bounded nonempty Thunderbird search text")
    if not 1 <= options.max_results <= 100:
        raise ValueError("max-results must be between 1 and 100")
    policy.require("mail.read", name=options.account)
    return _message(_mail(
        "search", options.account, query=options.query,
        folder=options.folder, max_results=options.max_results,
    ))


def cmd_read(args):
    parser = _account_parser("read")
    parser.add_argument("--id", required=True)
    options = parser.parse_args(args)
    if _message_account(options.id) != options.account:
        raise ValueError("message reference belongs to a different Thunderbird account")
    policy.require("mail.read", name=options.account)
    return _message(_mail("read", options.account, id=options.id))


def cmd_native_message(args):
    parser = _parser("native_message")
    parser.add_argument("--id", required=True)
    options = parser.parse_args(args)
    account = _message_account(options.id)
    return cmd_read([f"--account={account}", f"--id={options.id}"])


def cmd_native_draft(args):
    parser = _parser("native_draft")
    parser.add_argument("--id", required=True)
    options = parser.parse_args(args)
    account = _message_account(options.id)
    policy.require("mail.read", name=account)
    result = _mail("native_draft", account, id=options.id)
    if "error" not in result:
        draft = result["draft"]
        result = {**result, "draft": {
            **draft, "object": _reference("thunderbird-draft", draft["id"]),
            "message": _message(draft["message"]),
        }}
    return result


def _remember_sent(result, to, subject, body, cc=None):
    first = (body or "").strip().splitlines()
    snippet = first[0][:200] if first else ""
    text = f"Sent email to {to}: {subject}"
    if snippet:
        text += f" — {snippet}"
    tags = ["email", "sent", "thunderbird"]
    if cc:
        tags.append("cc")
    try:
        memory.remember(
            source="email", text=text, kind="event",
            entity_id=result.get("id"), tags=tags,
            link=_reference("thunderbird-message", result["id"]) if result.get("id") else None,
        )
    except memory.MemoryError:
        pass


def _outgoing_parser(command):
    parser = _account_parser(command)
    parser.add_argument("--to", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--cc")
    parser.add_argument("--request-id")
    return parser


def cmd_send(args):
    options = _outgoing_parser("send").parse_args(args)
    _headers(options)
    policy.require("mail.send", name=options.account)
    result = _mail(
        "send", options.account, to=options.to, subject=options.subject,
        body=options.body, cc=options.cc,
    )
    if result.get("sent"):
        _remember_sent(result, options.to, options.subject, options.body, options.cc)
    return _message(result)


def cmd_draft_save(args):
    parser = _outgoing_parser("draft_save")
    parser.add_argument("--id")
    parser.add_argument("--source-account", type=_account)
    options = parser.parse_args(args)
    _headers(options)
    if options.id:
        if not options.source_account or _message_account(options.id) != options.source_account:
            raise ValueError("draft replacement requires its explicit matching source-account")
        if options.source_account.partition(":")[0] != options.account.partition(":")[0]:
            raise ValueError("draft and sender must use the same Thunderbird profile")
    elif options.source_account:
        raise ValueError("source-account requires the stored draft id")
    policy.require("mail.draft", name=options.account)
    if options.id:
        policy.require("mail.read", name=options.source_account)
        policy.require("mail.draft", name=options.source_account)
    result = _mail(
        "draft_save", options.account, id=options.id, source_account=options.source_account,
        to=options.to, subject=options.subject, body=options.body, cc=options.cc,
    )
    if "error" not in result:
        result = {**result, "draft": {
            **result["draft"], "object": _reference("thunderbird-draft", result["draft"]["id"]),
        }}
    return result


def cmd_draft_send(args):
    parser = _account_parser("draft_send")
    parser.add_argument("--id", required=True)
    parser.add_argument("--sender-account", required=True, type=_account)
    parser.add_argument("--review", required=True)
    parser.add_argument("--confirm", nargs="?", const=True, required=True, choices=[True])
    parser.add_argument("--request-id")
    options = parser.parse_args(args)
    if _message_account(options.id) != options.account:
        raise ValueError("draft belongs to a different mailbox account")
    if options.account.partition(":")[0] != options.sender_account.partition(":")[0]:
        raise ValueError("draft and sender must use the same Thunderbird profile")
    if options.confirm is not True:
        raise ValueError("sending a saved draft requires explicit confirmation")
    if (
        len(options.review) != 71 or not options.review.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in options.review[7:])
    ):
        raise ValueError("draft send requires its current SHA-256 review fingerprint")
    policy.require("mail.read", name=options.account)
    policy.require("mail.draft", name=options.account)
    policy.require("mail.send", name=options.sender_account)
    return _message(_mail(
        "draft_send", options.account, id=options.id, sender_account=options.sender_account,
        review=options.review, confirm=True,
    ))


def cmd_attachment_file(args):
    parser = _parser("attachment_file")
    parser.add_argument("--path", required=True)
    options = parser.parse_args(args)
    path = safe_realpath(options.path)
    if not os.path.isabs(options.path) or path != options.path:
        raise ValueError("attachment file path must be absolute and canonical")
    policy.require("fs.meta", path=path)
    metadata = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("attachment path is not a regular file")
    return {
        "path": path, "size": metadata.st_size, "modified_ns": metadata.st_mtime_ns,
        "object": _reference("attachment-file", path),
    }


def cmd_attachment_download(args):
    parser = _account_parser("attachment_download")
    parser.add_argument("--id", required=True)
    parser.add_argument("--attachment", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-bytes", type=int, default=MAX_ATTACHMENT_BYTES)
    options = parser.parse_args(args)
    if _message_account(options.id) != options.account:
        raise ValueError("attachment message belongs to a different account")
    if not options.attachment.split(".") or any(
        not part or not part.isascii() or not part.isdigit()
        for part in options.attachment.split(".")
    ):
        raise ValueError("attachment must be its native MIME part identifier")
    if not 1 <= options.max_bytes <= MAX_ATTACHMENT_BYTES:
        raise ValueError("max-bytes must be between 1 and 16777216")
    path = safe_realpath(options.output)
    if not os.path.isabs(options.output) or path != options.output:
        raise ValueError("attachment output must be absolute and canonical")
    policy.require("mail.read", name=options.account)
    policy.require("fs.write", path=path)
    result = _mail(
        "attachment_download", options.account, id=options.id,
        attachment=options.attachment, output=path, max_bytes=options.max_bytes,
    )
    if "error" not in result:
        result = {**result, "object": _reference("attachment-file", result["path"]),
                  "source_message": _reference("thunderbird-message", options.id)}
    return result


def _private_directory(name):
    root = os.environ.get("COS_DATA_DIR")
    if not root or not os.path.isabs(root):
        raise ValueError("Mail storage requires the authenticated App data partition")
    directory = os.path.join(root, name)
    try:
        os.mkdir(directory, 0o700)
        _fsync_dir(root, strict=True)
    except FileExistsError:
        pass
    metadata = os.stat(directory, follow_symlinks=False)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
        raise ValueError("Mail storage must be a private owner-owned directory")
    return directory


def _read_record(path, limit=65536):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as source:
        metadata = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
            or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077
        ):
            raise ValueError("Mail storage record must be a private regular file")
        encoded = source.read(limit + 1)
    if len(encoded) > limit:
        raise ValueError("Mail storage record exceeds its bound")
    return json.loads(encoded)


def _lock(path):
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
        or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077
    ):
        os.close(descriptor)
        raise ValueError("Mail storage lock must be a private regular file")
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    return descriptor


def cmd_sync(args):
    parser = _account_parser("sync")
    parser.add_argument("--reset", action="store_true")
    options = parser.parse_args(args)
    policy.require("mail.read", name=options.account)
    policy.require("data.db.read", name="mail-sync")
    policy.require("data.db.write", name="mail-sync")
    directory = _private_directory("mail-sync")
    path = os.path.join(directory, "thunderbird-" + hashlib.sha256(options.account.encode()).hexdigest() + ".json")
    descriptor = _lock(path + ".lock")
    try:
        previous = _read_record(path, 8192)
        if previous is not None and (
            not isinstance(previous, dict) or set(previous) != {"account", "cursor"}
            or previous["account"] != options.account or type(previous["cursor"]) is not int
            or previous["cursor"] < 0
        ):
            raise ValueError("Thunderbird mailbox continuation is corrupt")
        result = _mail(
            "sync", options.account, reset=options.reset,
            cursor=previous["cursor"] if previous is not None and not options.reset else None,
        )
        if "error" in result:
            return result
        count = 0
        for item in result["messages"]:
            if _message_account(item["id"]) != options.account:
                raise ValueError("Thunderbird journal returned another account")
            reference = _reference("thunderbird-message", item["id"])
            key = "message-" + hashlib.sha256(
                json.dumps([options.account, item["sequence"], item["id"]]).encode()
            ).hexdigest()
            events.publish("message.received", key, payload={
                "provider": "thunderbird", "account": options.account, "object": reference,
            })
            count += 1
        atomic_write_json(path, {"account": options.account, "cursor": result["cursor"]}, mode=0o600, strict=True)
        return {
            "provider": "thunderbird", "account": options.account,
            "initialised": result["baseline"], "events_emitted": count, "more": False,
        }
    finally:
        os.close(descriptor)


_DRAFT_SYSTEMS = {
    "formal": (
        "Draft a polite, professional email reply based on the user's context. "
        "Use a courteous tone, complete sentences, and a clear sign-off. "
        "Return only the email body — no preamble, no subject line."
    ),
    "casual": (
        "Draft a friendly, conversational email reply based on the user's context. "
        "Keep it warm and approachable but still clear. "
        "Return only the email body — no preamble, no subject line."
    ),
    "short": (
        "Draft a very short, to-the-point email reply based on the user's context. "
        "Aim for 2-3 sentences maximum. "
        "Return only the email body — no preamble, no subject line."
    ),
}


def cmd_draft(args):
    parser = _parser("draft")
    parser.add_argument("--context", required=True)
    parser.add_argument("--style", default="formal", choices=["formal", "casual", "short"])
    options = parser.parse_args(args)
    if not options.context.strip():
        raise ValueError("context must be nonempty")
    policy.require("ai.chat", wild=True)
    try:
        response = ai.chat(
            prompt=options.context, origin="trusted",
            system=_DRAFT_SYSTEMS[options.style], max_units=3000,
        )
    except ai.AiBudgetExceeded as error:
        return {"error": "AI budget exceeded for this app", "detail": error.payload}
    except ai.AiSafetyViolation as error:
        return {"error": "safety violation", "detail": error.payload}
    except ai.AiDenied as error:
        return {"error": "AI call denied", "detail": error.payload}
    except ai.AiUnavailable as error:
        return {"error": f"AI unavailable: {error}"}
    except ai.AiError as error:
        return {"error": str(error)}
    return {
        "draft": response.text, "style": options.style,
        "model": response.model, "provider": response.provider,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens, "units": response.usage.units,
        },
        "budget": {
            "period": response.budget.period, "units_used": response.budget.units_used,
            "units_cap": response.budget.units_cap,
        },
        "review": {
            "safety": response.review.safety, "prompt_redacted": response.review.prompt_redacted,
        },
    }


def _request_guard(command, args, handler):
    request_id = None
    filtered = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--request-id" or token.startswith("--request-id="):
            if request_id is not None:
                raise ValueError("request-id must occur only once")
            if token == "--request-id":
                index += 1
                if index == len(args):
                    raise ValueError("request-id requires a canonical UUID")
                request_id = args[index]
            else:
                request_id = token.partition("=")[2]
        else:
            filtered.append(token)
        index += 1
    if request_id is None:
        return handler(args)
    if str(uuid.UUID(request_id)) != request_id:
        raise ValueError("request-id must be a canonical UUID")
    policy.require("data.db.read", name="mail-requests")
    policy.require("data.db.write", name="mail-requests")
    directory = _private_directory("mail-requests")
    fingerprint = hashlib.sha256(json.dumps(
        {"operation": command, "arguments": filtered}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    path = os.path.join(directory, request_id + ".json")
    descriptor = _lock(path + ".lock")
    try:
        previous = _read_record(path)
        if previous is not None:
            if not isinstance(previous, dict) or set(previous) != {"fingerprint", "state", "result"}:
                raise ValueError("Mail request record is corrupt")
            if previous["fingerprint"] != fingerprint:
                raise ValueError("request-id is already bound to a different Mail operation")
            if previous["state"] != "returned":
                return {
                    "error": "the previous Mail request outcome is unknown; inspect it before a new request",
                    "indeterminate": True, "retryable": False,
                }
            return previous["result"]
        if sum(name.endswith(".json") for name in os.listdir(directory)) >= 10000:
            raise ValueError("Mail submission history reached its retained request limit")
        record = {"fingerprint": fingerprint, "state": "in_flight", "result": None}
        atomic_write_json(path, record, mode=0o600, strict=True)
        result = handler(filtered)
        if isinstance(result, dict) and "error" in result:
            result = {**result, "indeterminate": True, "retryable": False}
        record.update(state="returned", result=result)
        try:
            atomic_write_json(path, record, mode=0o600, strict=True)
        except OSError as error:
            return {
                "error": f"Mail result recording failed; do not repeat the request: {error}",
                "indeterminate": True, "retryable": False, "result": result,
            }
        return result
    finally:
        os.close(descriptor)


def run(command, args):
    from canonical_argv import normalize_argparse_booleans
    args = normalize_argparse_booleans(args, bool_flags={"unread", "confirm", "reset"})
    handlers = {
        "accounts": cmd_accounts, "folders": cmd_folders,
        "sync": cmd_sync, "native_message": cmd_native_message, "native_draft": cmd_native_draft,
        "send": cmd_send, "search": cmd_search, "list": cmd_list, "read": cmd_read,
        "draft_save": cmd_draft_save, "draft_send": cmd_draft_send,
        "attachment_file": cmd_attachment_file, "attachment_download": cmd_attachment_download,
        "draft": cmd_draft,
    }
    handler = handlers.get(command)
    if handler is None:
        return {"error": f"unknown command: {command}"}
    if any(
        token.startswith("--") and token[2:].partition("=")[0] in {"provider", "host"}
        for token in args
    ):
        return {"error": "Email now uses Thunderbird; use email.accounts and an explicit --account"}
    try:
        result = _request_guard(command, args, handler) if command in {
            "send", "draft_save", "draft_send",
        } else handler(args)
        if command != "draft" and isinstance(result, dict):
            result = {**result, "provider": "thunderbird"}
        kinds = {
            "send": "message.sent", "draft_send": "message.sent",
            "draft_save": "draft.saved", "attachment_download": "attachment.downloaded",
        }
        if command in kinds and "error" not in result:
            reference = result.get("object") or result.get("draft", {}).get("object")
            payload = {"provider": "thunderbird", "account": result.get("account"), "object": reference}
            request_key = next(
                (token.partition("=")[2] for token in args if token.startswith("--request-id=")),
                None,
            )
            if request_key is None and "--request-id" in args:
                request_key = args[args.index("--request-id") + 1]
            if request_key is None and result.get("id") is None and reference is None:
                request_key = str(uuid.uuid4())
            key = "mutation-" + hashlib.sha256(json.dumps(
                {"operation": command, "payload": payload, "id": result.get("id"),
                 "draft_id": result.get("draft_id"), "request": request_key}, sort_keys=True,
            ).encode()).hexdigest()
            try:
                events.publish(kinds[command], key, payload=payload)
            except Exception as error:
                result = {**result, "event_error": str(error), "effects_not_repeated": True}
        return result
    except SystemExit:
        return {"error": "invalid Email arguments; use the declared Thunderbird tool schema"}
    except (ValueError, OSError) as error:
        return {"error": str(error)}
    except policy.PermissionDenied as error:
        return {"error": str(error), "denial": error.denial}
    except policy.PolicyUnavailable as error:
        return {"error": f"capability check failed: {error}"}
    except kernel.KernelDenied as error:
        return {"error": str(error), "denied": True}
    except kernel.KernelUnavailable as error:
        return {"error": str(error), "indeterminate": command in {"send", "draft_save", "draft_send"}, "retryable": False}
