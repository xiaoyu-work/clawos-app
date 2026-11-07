"""Legacy Mail SMTP/Gmail/Outlook operations, pending the native-engine cutover.

This implementation belongs to the Mail product, not an independent Agent
mailbox product. Source relocation preserves its existing identity and grants;
sharing Thunderbird account/object state requires the separate product cutover.
"""

import argparse
import base64
import hashlib
import json
import os
import smtplib
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import idna

from _shared.credentials import load_credential  # noqa: E402
from _shared.atomic import atomic_create_bytes, _fsync_dir  # noqa: E402
from _shared.paths import safe_realpath  # noqa: E402
from _shared.safe_http import open_url  # noqa: E402
from claw_os_sdk import ai  # noqa: E402
from claw_os_sdk.objects import ObjectRefError, format_reference  # noqa: E402
from claw_os_sdk.mcp import current_context  # noqa: E402
from cos_runtime import memory, policy, snapshot  # noqa: E402
from cos_runtime import smtp as cos_smtp  # noqa: E402


# ---------------------------------------------------------------------------
# Provider host map — used for fine-grained net.dial scoping
# ---------------------------------------------------------------------------

GMAIL_API_HOST = "gmail.googleapis.com"
OUTLOOK_API_HOST = "graph.microsoft.com"
GOOGLE_ACCESS_TOKEN = "GOOGLE_ACCESS_TOKEN"
MICROSOFT_ACCESS_TOKEN = "MICROSOFT_ACCESS_TOKEN"
MAX_ATTACHMENT_BYTES = 16 * 1024 * 1024


def _credential_value(store_name, *legacy_env_names):
    value = os.environ.get(store_name)
    if value:
        return value, None
    for name in legacy_env_names:
        value = os.environ.get(name)
        if value:
            return value, None
    return load_credential(store_name)


def _gmail_auth_error(detail, status=None):
    result = {
        "error": "Gmail authorization is required or has expired",
        "provider": "gmail",
        "auth_required": True,
        "retryable": False,
        "credential": f"default/{GOOGLE_ACCESS_TOKEN}",
        "detail": detail,
        "setup": {
            "interactive_oauth_available": True,
            "agent_action": {
                "tool": "cos_oauth_login",
                "input": {"provider": "google"},
            },
            "login_command": "cos credential oauth-login google",
            "message": (
                "The system Agent should start the trusted browser authorization "
                "with setup.agent_action. The login command is a terminal fallback."
            ),
        },
    }
    if status is not None:
        result["status"] = status
    return result


def _outlook_auth_error(detail, status=None):
    result = {
        "error": "Outlook authorization is required or has expired",
        "provider": "outlook",
        "auth_required": True,
        "retryable": False,
        "credential": f"default/{MICROSOFT_ACCESS_TOKEN}",
        "detail": detail,
        "setup": {
            "interactive_oauth_available": True,
            "agent_action": {
                "tool": "cos_oauth_login",
                "input": {"provider": "microsoft"},
            },
            "login_command": "cos credential oauth-login microsoft",
            "message": (
                "The system Agent should start the trusted browser authorization "
                "with setup.agent_action. The login command is a terminal fallback."
            ),
        },
    }
    if status is not None:
        result["status"] = status
    return result


# ---------------------------------------------------------------------------
# Argument parsers
# ---------------------------------------------------------------------------

def _build_send_parser():
    p = argparse.ArgumentParser(prog="cos email send", add_help=False)
    p.add_argument("--to", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--cc", default=None)
    p.add_argument("--provider", required=True, choices=["smtp", "gmail", "outlook"])
    p.add_argument("--host", default=None, help="SMTP endpoint, e.g. mail.example.com:587")
    return p


def _build_search_parser():
    p = argparse.ArgumentParser(prog="cos email search", add_help=False)
    p.add_argument("--query", required=True)
    p.add_argument("--max-results", type=int, default=10)
    p.add_argument("--provider", required=True, choices=["gmail", "outlook"])
    return p


def _build_list_parser():
    p = argparse.ArgumentParser(prog="cos email list", add_help=False)
    p.add_argument("--max-results", type=int, default=10)
    p.add_argument("--unread", action="store_true")
    p.add_argument("--provider", required=True, choices=["gmail", "outlook"])
    return p


def _build_read_parser():
    p = argparse.ArgumentParser(prog="cos email read", add_help=False)
    p.add_argument("--id", required=True, dest="message_id")
    p.add_argument("--provider", required=True, choices=["gmail", "outlook"])
    return p


def _message_reference(provider, message_id):
    return format_reference({
        "app_id": "email",
        "object_type": f"{provider}-message",
        "object_id": message_id,
    })


def _read_message_object(provider, args):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--id", required=True)
    try:
        opts = parser.parse_args(args)
    except SystemExit:
        return {"error": f"usage: email {provider}_message --id <message-id>"}
    return cmd_read(["--provider", provider, f"--id={opts.id}"])


def cmd_gmail_message(args):
    return _read_message_object("gmail", args)


def cmd_outlook_message(args):
    return _read_message_object("outlook", args)


def _message_parts(payload):
    pending = [payload]
    count = 0
    while pending:
        part = pending.pop()
        count += 1
        if count > 1000:
            raise ValueError("message exceeds the 1000-part MIME limit")
        yield part
        pending.extend(reversed(part.get("parts", [])))


def _decode_attachment(encoded, limit):
    if not isinstance(encoded, str) or len(encoded) > ((limit + 2) // 3) * 4 + 4:
        raise ValueError("attachment exceeds its size limit")
    data = base64.b64decode(
        encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True,
    )
    if len(data) > limit:
        raise ValueError("attachment exceeds its size limit")
    return data


def _attachment_file_reference(path):
    return format_reference({
        "app_id": "email", "object_type": "attachment-file", "object_id": path,
    })


def cmd_attachment_file(args):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--path", required=True)
    try:
        options = parser.parse_args(args)
    except SystemExit:
        return {"error": "usage: email attachment_file --path <absolute-path>"}
    path = safe_realpath(options.path)
    if not os.path.isabs(options.path) or path != options.path:
        return {"error": "attachment file path must be absolute and canonical"}
    policy.require("fs.meta", path=path)
    metadata = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(metadata.st_mode):
        return {"error": "attachment path is not a regular file"}
    return {
        "path": path, "size": metadata.st_size, "modified_ns": metadata.st_mtime_ns,
        "object": _attachment_file_reference(path),
    }


def cmd_attachment_download(args):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--provider", choices=["gmail", "outlook"], required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--attachment", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-bytes", dest="max_bytes", type=int, default=MAX_ATTACHMENT_BYTES)
    try:
        options = parser.parse_args(args)
    except SystemExit:
        return {"error": "usage: email attachment_download --provider gmail|outlook --id MESSAGE --attachment ID --output PATH"}
    try:
        _message_reference(options.provider, options.id)
        format_reference({
            "app_id": "email", "object_type": "attachment", "object_id": options.attachment,
        })
        if not 1 <= options.max_bytes <= MAX_ATTACHMENT_BYTES:
            raise ValueError("max-bytes must be between 1 and 16777216")
        path = safe_realpath(options.output)
        if not os.path.isabs(options.output) or path != options.output:
            raise ValueError("output must be an absolute canonical path")
        _attachment_file_reference(path)
    except ValueError as error:
        return {"error": str(error)}
    policy.require("fs.write", path=path)
    if os.path.lexists(path):
        return {"error": "attachment output already exists; it will not be overwritten"}
    if not os.path.isdir(os.path.dirname(path)):
        return {"error": "attachment output parent must already exist"}
    message = urllib.parse.quote(options.id, safe="")
    attachment = urllib.parse.quote(options.attachment, safe="")
    if options.provider == "gmail":
        policy.require("secret.read", name="default/GOOGLE_ACCESS_TOKEN")
        policy.require("net.dial", host=GMAIL_API_HOST)
        if options.attachment.startswith("part:"):
            result = _gmail_request(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message}?format=full"
            )
            if "error" in result:
                return result
            result = next(
                (part["body"] for part in _message_parts(result.get("payload", {}))
                 if part.get("filename") and f"part:{part.get('partId')}" == options.attachment),
                {"error": "inline attachment part was not found"},
            )
        else:
            result = _gmail_request(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message}/attachments/{attachment}"
            )
        encoded = result.get("data")
    else:
        policy.require("secret.read", name="default/MICROSOFT_ACCESS_TOKEN")
        policy.require("net.dial", host=OUTLOOK_API_HOST)
        result = _outlook_request(
            f"https://graph.microsoft.com/v1.0/me/messages/{message}/attachments/{attachment}"
        )
        if result.get("@odata.type", "#microsoft.graph.fileAttachment") != "#microsoft.graph.fileAttachment":
            return {"error": "only Outlook file attachments can be downloaded"}
        encoded = result.get("contentBytes")
    if "error" in result:
        return result
    try:
        data = _decode_attachment(encoded, options.max_bytes)
    except ValueError as error:
        return {"error": str(error)}
    try:
        context = current_context()
    except RuntimeError:
        context = None
    if context is not None and context.session_id:
        snapshot.snapshot(path, "attachment_download", session_id=context.session_id)
    try:
        atomic_create_bytes(path, data, mode=0o600)
        _fsync_dir(os.path.dirname(path), strict=True)
    except FileExistsError:
        return {"error": "attachment output already exists; it will not be overwritten"}
    except OSError as error:
        return {
            "error": f"attachment persistence failed: {error}",
            "indeterminate": os.path.lexists(path), "path": path,
        }
    return {
        "provider": options.provider, "id": options.id, "attachment": options.attachment,
        "path": path, "bytes": len(data), "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
        "object": _attachment_file_reference(path),
        "source_message": _message_reference(options.provider, options.id),
    }


def _build_draft_parser():
    p = argparse.ArgumentParser(prog="cos email draft", add_help=False)
    p.add_argument("--context", required=True)
    p.add_argument(
        "--style",
        default="formal",
        choices=["formal", "casual", "short"],
    )
    return p


def _draft_reference(provider, draft_id):
    return format_reference({
        "app_id": "email", "object_type": f"{provider}-draft", "object_id": draft_id,
    })


def _authorize_mailbox(provider):
    if provider == "gmail":
        policy.require("secret.read", name="default/GOOGLE_ACCESS_TOKEN")
        policy.require("net.dial", host=GMAIL_API_HOST)
    else:
        policy.require("secret.read", name="default/MICROSOFT_ACCESS_TOKEN")
        policy.require("net.dial", host=OUTLOOK_API_HOST)


def _draft_view(provider, draft_id, message):
    raw = json.dumps(message, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    parsed = _parse_gmail_message(message) if provider == "gmail" else _parse_outlook_message(message)
    return {
        "id": draft_id, "object": _draft_reference(provider, draft_id),
        "review": "sha256:" + hashlib.sha256(raw).hexdigest(), "message": parsed,
    }


def _fetch_draft(provider, draft_id):
    encoded = urllib.parse.quote(draft_id, safe="")
    if provider == "gmail":
        result = _gmail_request(
            f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{encoded}?format=full"
        )
        if "error" in result:
            return result
        message = result.get("message", {})
    else:
        result = _outlook_request(
            f"https://graph.microsoft.com/v1.0/me/messages/{encoded}?$expand=attachments"
        )
        if "error" in result:
            return result
        if result.get("isDraft") is not True:
            return {"error": "the selected Outlook message is not a draft"}
        message = result
    return {"provider": provider, "draft": _draft_view(provider, draft_id, message)}


def _read_draft_object(provider, args):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--id", required=True)
    try:
        options = parser.parse_args(args)
        _draft_reference(provider, options.id)
    except (SystemExit, ValueError):
        return {"error": f"usage: email {provider}_draft --id <draft-id>"}
    _authorize_mailbox(provider)
    return _fetch_draft(provider, options.id)


def cmd_gmail_draft(args):
    return _read_draft_object("gmail", args)


def cmd_outlook_draft(args):
    return _read_draft_object("outlook", args)


def cmd_draft_save(args):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--provider", required=True, choices=["gmail", "outlook"])
    parser.add_argument("--id")
    parser.add_argument("--to", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--cc")
    try:
        options = parser.parse_args(args)
        if any("\r" in value or "\n" in value for value in (options.to, options.subject, options.cc or "")):
            raise ValueError("draft address and subject headers must not contain newlines")
        if options.id is not None:
            _draft_reference(options.provider, options.id)
    except (SystemExit, ValueError) as error:
        return {"error": f"invalid draft save arguments: {error}"}
    _authorize_mailbox(options.provider)
    if options.provider == "gmail":
        message = MIMEMultipart()
        message["To"] = options.to
        message["Subject"] = options.subject
        if options.cc:
            message["Cc"] = options.cc
        message.attach(MIMEText(options.body, "plain"))
        data = {"message": {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}}
        url = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
        if options.id is not None:
            data["id"] = options.id
            url += "/" + urllib.parse.quote(options.id, safe="")
        result = _gmail_request(url, method="PUT" if options.id is not None else "POST", data=data)
    else:
        data = {
            "subject": options.subject,
            "body": {"contentType": "Text", "content": options.body},
            "toRecipients": [
                {"emailAddress": {"address": address.strip()}}
                for address in options.to.split(",") if address.strip()
            ],
        }
        if options.cc:
            data["ccRecipients"] = [
                {"emailAddress": {"address": address.strip()}}
                for address in options.cc.split(",") if address.strip()
            ]
        url = "https://graph.microsoft.com/v1.0/me/messages"
        if options.id is not None:
            existing = _fetch_draft(options.provider, options.id)
            if "error" in existing:
                return existing
            url += "/" + urllib.parse.quote(options.id, safe="")
        result = _outlook_request(url, method="PATCH" if options.id is not None else "POST", data=data)
    if "error" in result:
        return result
    draft_id = result.get("id")
    if not draft_id:
        return {"error": "provider did not return a saved draft ID", "indeterminate": True}
    return {
        "saved": True, "sent": False, "provider": options.provider,
        "draft": {"id": draft_id, "object": _draft_reference(options.provider, draft_id)},
    }


def cmd_draft_send(args):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--provider", required=True, choices=["gmail", "outlook"])
    parser.add_argument("--id", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--confirm", nargs="?", const=True, required=True)
    try:
        options = parser.parse_args(args)
        _draft_reference(options.provider, options.id)
        if options.confirm is not True:
            raise ValueError("draft send requires explicit confirmation")
    except (SystemExit, ValueError) as error:
        return {"error": f"invalid draft send arguments: {error}"}
    _authorize_mailbox(options.provider)
    current = _fetch_draft(options.provider, options.id)
    if "error" in current:
        return current
    if options.review != current["draft"]["review"]:
        return {"error": "draft changed; read and review it again before sending", "conflicted": True}
    if options.provider == "gmail":
        result = _gmail_request(
            "https://gmail.googleapis.com/gmail/v1/users/me/drafts/send",
            method="POST", data={"id": options.id},
        )
    else:
        result = _outlook_request(
            f"https://graph.microsoft.com/v1.0/me/messages/{urllib.parse.quote(options.id, safe='')}/send",
            method="POST",
        )
    if "error" in result:
        return result
    return {
        "sent": True, "provider": options.provider, "draft_id": options.id,
        "id": result.get("id"), "delivery_confirmed": False,
    }


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


# ---------------------------------------------------------------------------
# SMTP send
# ---------------------------------------------------------------------------

def _smtp_connection(host, port, timeout=30):
    """Open an SMTP session over whatever transport this worker has.

    Inside a sandbox the process cannot dial TCP at all, so the session
    is carried by the brokered egress tunnel: the broker checks
    ``host:port`` against the operation's exact ``net.dial`` grant,
    resolves the name itself and refuses any address that is not
    globally routable. `cos_runtime.smtp` substitutes the transport at
    `smtplib`'s own extension point, so there is no path left that could
    fall back to a direct dial. Outside a sandbox it is the ordinary
    :class:`smtplib.SMTP` dial, unchanged.
    """
    return cos_smtp.connect(
        host,
        port,
        timeout=timeout,
        implicit_tls=port == 465,
        starttls=port == 587,
    )


def _smtp_endpoint(value):
    host, separator, port = value.rpartition(":")
    if (
        not separator
        or not host
        or ":" in host
        or not value.isascii()
        or not port.isdecimal()
        or len(port) > 5
    ):
        raise ValueError("SMTP requires an explicit host:port")
    port = int(port)
    if not 1 <= port <= 65535 or host.endswith("."):
        raise ValueError("invalid SMTP host or port")
    host = idna.encode(host, uts46=True, std3_rules=True).decode("ascii")
    return host.lower(), port


def _send_smtp(to, subject, body, host, port, cc=None):
    """Send an email via SMTP."""
    user = os.environ.get("SMTP_USER", "")
    password, _ = _credential_value("SMTP_PASSWORD")
    password = password or ""
    from_addr = os.environ.get("SMTP_FROM", user)

    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    msg.attach(MIMEText(body, "plain"))

    with _smtp_connection(host, port) as server:
        if user and password:
            server.login(user, password)
        server.send_message(msg)

    return {"sent": True, "to": to, "subject": subject, "provider": "smtp"}


# ---------------------------------------------------------------------------
# Gmail helpers
# ---------------------------------------------------------------------------

def _gmail_token():
    return _credential_value(
        GOOGLE_ACCESS_TOKEN,
        "GMAIL_ACCESS_TOKEN",
        "GOOGLE_OAUTH_TOKEN",
    )


def _gmail_request(url, method="GET", data=None):
    """Make an authenticated request to the Gmail API."""
    token, credential_error = _gmail_token()
    if not token:
        return _gmail_auth_error(
            credential_error or f"missing default/{GOOGLE_ACCESS_TOKEN}"
        )
    headers = {"Authorization": f"Bearer {token}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data).encode("utf-8") if isinstance(data, dict) else data
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with open_url(req, timeout=30)[0] as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        finally:
            e.close()
        if e.code == 401:
            return _gmail_auth_error(err_body or str(e), status=e.code)
        return {"error": err_body or str(e), "status": e.code}
    except urllib.error.URLError as e:
        return {"error": str(e.reason)}
    except Exception as e:
        return {"error": str(e)}


def _send_gmail(to, subject, body, cc=None):
    """Send an email via the Gmail API."""
    msg = MIMEMultipart()
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    msg.attach(MIMEText(body, "plain"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    result = _gmail_request(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        method="POST",
        data={"raw": raw},
    )
    if "error" in result:
        return result
    return {
        "sent": True,
        "to": to,
        "subject": subject,
        "provider": "gmail",
        "id": result.get("id", ""),
    }


def _parse_gmail_message(msg_data):
    """Extract structured fields from a Gmail API message resource."""
    headers = {}
    for h in msg_data.get("payload", {}).get("headers", []):
        headers[h["name"].lower()] = h["value"]

    snippet = msg_data.get("snippet", "")
    labels = msg_data.get("labelIds", [])
    unread = "UNREAD" in labels

    # Extract plain-text body from parts or payload body
    body = ""
    payload = msg_data.get("payload", {})
    if payload.get("body", {}).get("data"):
        body = _decode_attachment(payload["body"]["data"], MAX_ATTACHMENT_BYTES).decode(
            "utf-8", errors="replace"
        )
    else:
        for part in _message_parts(payload):
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                body = _decode_attachment(part["body"]["data"], MAX_ATTACHMENT_BYTES).decode(
                    "utf-8", errors="replace"
                )
                break

    # Attachments
    attachments = []
    for part in _message_parts(payload):
        filename = part.get("filename")
        if filename:
            attachments.append({
                "name": filename,
                "size": part.get("body", {}).get("size", 0),
                "id": part.get("body", {}).get("attachmentId") or (
                    f"part:{part['partId']}" if part.get("partId") is not None else None
                ),
                "content_type": part.get("mimeType", ""),
            })

    result = {
        "id": msg_data.get("id", ""),
        "from": headers.get("from", ""),
        "to": [a.strip() for a in headers.get("to", "").split(",") if a.strip()],
        "cc": [a.strip() for a in headers.get("cc", "").split(",") if a.strip()],
        "bcc": [a.strip() for a in headers.get("bcc", "").split(",") if a.strip()],
        "subject": headers.get("subject", ""),
        "snippet": snippet,
        "body": body,
        "date": headers.get("date", ""),
        "unread": unread,
        "attachments": attachments,
    }
    if result["id"]:
        result["object"] = _message_reference("gmail", result["id"])
    return result


def _search_gmail(query, max_results):
    """Search emails via the Gmail API."""
    url = (
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages"
        f"?q={urllib.request.quote(query)}&maxResults={max_results}"
    )
    result = _gmail_request(url)
    if "error" in result:
        return result

    messages = result.get("messages", [])
    emails = []
    for m in messages:
        detail = _gmail_request(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}"
            f"?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date"
        )
        if "error" in detail:
            if detail.get("auth_required") or detail.get("retryable") is False:
                return detail
            continue
        parsed = _parse_gmail_message(detail)
        emails.append({
            "id": parsed["id"],
            "from": parsed["from"],
            "subject": parsed["subject"],
            "snippet": parsed["snippet"],
            "date": parsed["date"],
            "unread": parsed["unread"],
            "object": parsed.get("object"),
        })

    return {"query": query, "provider": "gmail", "emails": emails, "count": len(emails)}


def _list_gmail(max_results, unread):
    """List recent emails via the Gmail API."""
    query = "is:unread" if unread else ""
    url = (
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages"
        f"?maxResults={max_results}"
    )
    if query:
        url += f"&q={urllib.request.quote(query)}"
    result = _gmail_request(url)
    if "error" in result:
        return result

    messages = result.get("messages", [])
    emails = []
    for m in messages:
        detail = _gmail_request(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}"
            f"?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date"
        )
        if "error" in detail:
            if detail.get("auth_required") or detail.get("retryable") is False:
                return detail
            continue
        parsed = _parse_gmail_message(detail)
        emails.append({
            "id": parsed["id"],
            "from": parsed["from"],
            "subject": parsed["subject"],
            "snippet": parsed["snippet"],
            "date": parsed["date"],
            "unread": parsed["unread"],
            "object": parsed.get("object"),
        })

    return {"provider": "gmail", "emails": emails, "count": len(emails)}


def _read_gmail(message_id):
    """Read a specific email via the Gmail API."""
    url = (
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{urllib.parse.quote(message_id, safe='')}"
        f"?format=full"
    )
    result = _gmail_request(url)
    if "error" in result:
        return result
    return _parse_gmail_message(result)


# ---------------------------------------------------------------------------
# Outlook helpers
# ---------------------------------------------------------------------------

def _outlook_token():
    return _credential_value(MICROSOFT_ACCESS_TOKEN, "MICROSOFT_OAUTH_TOKEN")


def _outlook_request(url, method="GET", data=None):
    """Make an authenticated request to the Microsoft Graph API."""
    token, credential_error = _outlook_token()
    if not token:
        return _outlook_auth_error(
            credential_error or f"missing default/{MICROSOFT_ACCESS_TOKEN}"
        )
    headers = {"Authorization": f"Bearer {token}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data).encode("utf-8") if isinstance(data, dict) else data
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with open_url(req, timeout=30)[0] as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        finally:
            e.close()
        if e.code == 401:
            return _outlook_auth_error(err_body or str(e), status=e.code)
        return {"error": err_body or str(e), "status": e.code}
    except urllib.error.URLError as e:
        return {"error": str(e.reason)}
    except Exception as e:
        return {"error": str(e)}


def _send_outlook(to, subject, body, cc=None):
    """Send an email via the Microsoft Graph API."""
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        }
    }
    if cc:
        payload["message"]["ccRecipients"] = [{"emailAddress": {"address": cc}}]

    result = _outlook_request(
        "https://graph.microsoft.com/v1.0/me/sendMail",
        method="POST",
        data=payload,
    )
    if "error" in result:
        return result
    return {"sent": True, "to": to, "subject": subject, "provider": "outlook"}


def _parse_outlook_message(msg_data):
    """Extract structured fields from an Outlook Graph API message resource."""
    from_field = msg_data.get("from", {}).get("emailAddress", {})
    to_list = [
        r.get("emailAddress", {}).get("address", "")
        for r in msg_data.get("toRecipients", [])
    ]
    attachments = [
        {"id": a.get("id"), "name": a.get("name", ""), "size": a.get("size", 0),
         "content_type": a.get("contentType", "")}
        for a in msg_data.get("attachments", [])
    ]
    result = {
        "id": msg_data.get("id", ""),
        "from": from_field.get("address", ""),
        "to": to_list,
        "cc": [r.get("emailAddress", {}).get("address", "") for r in msg_data.get("ccRecipients", [])],
        "bcc": [r.get("emailAddress", {}).get("address", "") for r in msg_data.get("bccRecipients", [])],
        "subject": msg_data.get("subject", ""),
        "snippet": msg_data.get("bodyPreview", ""),
        "body": msg_data.get("body", {}).get("content", ""),
        "date": msg_data.get("receivedDateTime", ""),
        "unread": not msg_data.get("isRead", True),
        "attachments": attachments,
    }
    if result["id"]:
        result["object"] = _message_reference("outlook", result["id"])
    return result


def _search_outlook(query, max_results):
    """Search emails via the Microsoft Graph API."""
    encoded_query = urllib.request.quote(query)
    url = (
        f"https://graph.microsoft.com/v1.0/me/messages"
        f"?$search=%22{encoded_query}%22&$top={max_results}"
    )
    result = _outlook_request(url)
    if "error" in result:
        return result

    messages = result.get("value", [])
    emails = []
    for m in messages:
        parsed = _parse_outlook_message(m)
        emails.append({
            "id": parsed["id"],
            "from": parsed["from"],
            "subject": parsed["subject"],
            "snippet": parsed["snippet"],
            "date": parsed["date"],
            "unread": parsed["unread"],
            "object": parsed.get("object"),
        })

    return {"query": query, "provider": "outlook", "emails": emails, "count": len(emails)}


def _list_outlook(max_results, unread):
    """List recent emails via the Microsoft Graph API."""
    url = f"https://graph.microsoft.com/v1.0/me/messages?$top={max_results}"
    if unread:
        url += "&$filter=isRead%20eq%20false"
    url += "&$orderby=receivedDateTime%20desc"
    result = _outlook_request(url)
    if "error" in result:
        return result

    messages = result.get("value", [])
    emails = []
    for m in messages:
        parsed = _parse_outlook_message(m)
        emails.append({
            "id": parsed["id"],
            "from": parsed["from"],
            "subject": parsed["subject"],
            "snippet": parsed["snippet"],
            "date": parsed["date"],
            "unread": parsed["unread"],
            "object": parsed.get("object"),
        })

    return {"provider": "outlook", "emails": emails, "count": len(emails)}


def _read_outlook(message_id):
    """Read a specific email via the Microsoft Graph API."""
    url = (
        f"https://graph.microsoft.com/v1.0/me/messages/{urllib.parse.quote(message_id, safe='')}"
        "?$expand=attachments($select=id,name,size,contentType)"
    )
    result = _outlook_request(url)
    if "error" in result:
        return result
    return _parse_outlook_message(result)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _remember_sent(result, to, subject, body, cc=None):
    """Push a one-line summary of a sent email into the agent's memory."""
    try:
        provider = result.get("provider") or "smtp"
        message_id = result.get("id") or ""
        snippet = (body or "").strip().splitlines()
        first = snippet[0] if snippet else ""
        if len(first) > 200:
            first = first[:197] + "..."
        text = f"Sent email to {to}: {subject}".strip()
        if first:
            text += f" — {first}"
        tags = ["email", "sent", provider]
        if cc:
            tags.append("cc")
        memory.remember(
            source="email",
            text=text,
            kind="event",
            entity_id=message_id or None,
            tags=tags,
            link=_message_reference(provider, message_id) if message_id else None,
        )
    except memory.MemoryError:
        pass


def cmd_send(args):
    parser = _build_send_parser()
    try:
        opts = parser.parse_args(args)
    except SystemExit:
        return {"error": "missing required arguments: --to, --subject, --body"}

    provider = opts.provider
    if provider == "smtp":
        if not opts.host:
            return {"error": "missing required argument: --host for smtp provider"}
        try:
            host, port = _smtp_endpoint(opts.host)
        except ValueError:
            return {
                "error": "invalid SMTP --host: use an explicit DNS name or IPv4 address "
                "and port, e.g. mail.example.com:587 (STARTTLS) or mail.example.com:465 (TLS)"
            }
        policy.require("secret.read", name="default/SMTP_PASSWORD")
        policy.require("net.dial", host=opts.host)
        result = _send_smtp(
            opts.to, opts.subject, opts.body, host, port, cc=opts.cc
        )
    elif provider == "gmail":
        policy.require("secret.read", name="default/GOOGLE_ACCESS_TOKEN")
        policy.require("net.dial", host=GMAIL_API_HOST)
        result = _send_gmail(opts.to, opts.subject, opts.body, cc=opts.cc)
    elif provider == "outlook":
        policy.require("secret.read", name="default/MICROSOFT_ACCESS_TOKEN")
        policy.require("net.dial", host=OUTLOOK_API_HOST)
        result = _send_outlook(opts.to, opts.subject, opts.body, cc=opts.cc)
    else:
        return {"error": f"unknown provider: {provider}"}

    if isinstance(result, dict) and result.get("sent"):
        _remember_sent(result, opts.to, opts.subject, opts.body, cc=opts.cc)
    return result


def cmd_search(args):
    parser = _build_search_parser()
    try:
        opts = parser.parse_args(args)
    except SystemExit:
        return {"error": "missing required argument: --query"}

    provider = opts.provider
    if provider == "gmail":
        policy.require("secret.read", name="default/GOOGLE_ACCESS_TOKEN")
        policy.require("net.dial", host=GMAIL_API_HOST)
        return _search_gmail(opts.query, opts.max_results)
    elif provider == "outlook":
        policy.require("secret.read", name="default/MICROSOFT_ACCESS_TOKEN")
        policy.require("net.dial", host=OUTLOOK_API_HOST)
        return _search_outlook(opts.query, opts.max_results)
    else:
        return {"error": f"unknown provider: {provider}"}


def cmd_list(args):
    parser = _build_list_parser()
    try:
        opts = parser.parse_args(args)
    except SystemExit:
        return {"error": "invalid arguments for list command"}

    provider = opts.provider
    if provider == "gmail":
        policy.require("secret.read", name="default/GOOGLE_ACCESS_TOKEN")
        policy.require("net.dial", host=GMAIL_API_HOST)
        return _list_gmail(opts.max_results, opts.unread)
    elif provider == "outlook":
        policy.require("secret.read", name="default/MICROSOFT_ACCESS_TOKEN")
        policy.require("net.dial", host=OUTLOOK_API_HOST)
        return _list_outlook(opts.max_results, opts.unread)
    else:
        return {"error": f"unknown provider: {provider}"}


def cmd_read(args):
    parser = _build_read_parser()
    try:
        opts = parser.parse_args(args)
    except SystemExit:
        return {"error": "missing required argument: --id"}

    provider = opts.provider
    try:
        _message_reference(provider, opts.message_id)
    except ObjectRefError as error:
        return {"error": f"invalid message ID: {error}"}
    if provider == "gmail":
        policy.require("secret.read", name="default/GOOGLE_ACCESS_TOKEN")
        policy.require("net.dial", host=GMAIL_API_HOST)
        return _read_gmail(opts.message_id)
    elif provider == "outlook":
        policy.require("secret.read", name="default/MICROSOFT_ACCESS_TOKEN")
        policy.require("net.dial", host=OUTLOOK_API_HOST)
        return _read_outlook(opts.message_id)
    else:
        return {"error": f"unknown provider: {provider}"}


def cmd_draft(args):
    """Draft an email reply via the AI gate. Pure text — does NOT send."""
    parser = _build_draft_parser()
    try:
        opts = parser.parse_args(args)
    except SystemExit:
        return {"error": "usage: cos email draft --context <text> [--style formal|casual|short]"}

    if not opts.context.strip():
        return {"error": "--context must be non-empty"}

    # Coarse-grained capability check — fail fast on a denied agent.
    policy.require("ai.chat", wild=True)

    system_prompt = _DRAFT_SYSTEMS.get(opts.style, _DRAFT_SYSTEMS["formal"])

    try:
        response = ai.chat(
            prompt=opts.context,
            origin="trusted",
            system=system_prompt,
            max_units=3000,
        )
    except ai.AiBudgetExceeded as exc:
        return {"error": "AI budget exceeded for this app", "detail": exc.payload}
    except ai.AiSafetyViolation as exc:
        return {"error": "safety violation", "detail": exc.payload}
    except ai.AiDenied as exc:
        return {"error": "AI call denied", "detail": exc.payload}
    except ai.AiUnavailable as exc:
        return {"error": f"AI unavailable: {exc}"}
    except ai.AiError as exc:
        return {"error": str(exc)}

    return {
        "draft": response.text,
        "style": opts.style,
        "model": response.model,
        "provider": response.provider,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "units": response.usage.units,
        },
        "budget": {
            "period": response.budget.period,
            "units_used": response.budget.units_used,
            "units_cap": response.budget.units_cap,
        },
        "review": {
            "safety": response.review.safety,
            "prompt_redacted": response.review.prompt_redacted,
        },
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(command, args):
    """Entry point called by cos."""
    from canonical_argv import normalize_argparse_booleans
    args = normalize_argparse_booleans(args, bool_flags={"unread", "confirm"})
    handlers = {
        "draft_save": cmd_draft_save,
        "draft_send": cmd_draft_send,
        "gmail_draft": cmd_gmail_draft,
        "outlook_draft": cmd_outlook_draft,
        "attachment_file": cmd_attachment_file,
        "attachment_download": cmd_attachment_download,
        "gmail_message": cmd_gmail_message,
        "outlook_message": cmd_outlook_message,
        "send": cmd_send,
        "search": cmd_search,
        "list": cmd_list,
        "read": cmd_read,
        "draft": cmd_draft,
    }
    handler = handlers.get(command)
    if handler is None:
        return {"error": f"unknown command: {command}"}
    try:
        return handler(args)
    except policy.PermissionDenied as denied:
        return {"error": str(denied), "denial": denied.denial}
    except policy.PolicyUnavailable as exc:
        return {"error": f"capability check failed: {exc}"}
