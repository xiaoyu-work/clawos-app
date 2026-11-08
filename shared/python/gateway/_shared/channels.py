"""Presentation-only client; Root owns channel admission and replay evidence."""

from claw_os_sdk import channels
from claw_os_sdk.mcp import current_context
from canonical_argv import parse_canonical_argv


def run(platform, action, args):
    options = {}
    if action == "reply":
        if isinstance(args, dict):
            event_id, text, confirm = args.get("event_id"), args.get("text"), args.get("confirm")
        elif isinstance(args, list):
            try:
                positionals, flags = parse_canonical_argv(args, bool_flags=("confirm",))
            except ValueError as error:
                return {"ok": False, "platform": platform, "error": str(error)}
            if len(positionals) < 2:
                return {"ok": False, "platform": platform, "error": "reply requires event_id and text"}
            event_id, text, confirm = positionals[0], " ".join(positionals[1:]), flags.get("confirm")
        else:
            return {"ok": False, "platform": platform, "error": "reply requires event_id, text and confirmation"}
        if confirm is not True and str(confirm).lower() != "true":
            return {"ok": False, "platform": platform, "error": "reply requires confirm=true"}
        text = " ".join(str(part) for part in text) if isinstance(text, list) else text
        options = {"event_id": event_id, "text": text, "confirm": True}
    try:
        context = current_context()
    except RuntimeError:
        context = None
    if context is not None:
        options.update(deadline_unix_ms=context.deadline_unix_ms, check_cancelled=context.raise_if_cancelled)
    try:
        return channels.control(action, **options)
    except Exception as error:
        result = {"ok": False, "platform": platform, "error": str(error)}
        if getattr(error, "denial", None) is not None:
            result["denial"] = error.denial
        return result
