"""Send closed desktop requests through the authenticated OS service."""

import re
import sys
import time

from claw_os_sdk.generated import encode_wire_json
from claw_os_sdk.kernel import (
    KernelDenied,
    KernelUnavailable,
    call_json_with_stdin_binary,
)


APP_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}")


WINDOW_RE = re.compile(r"[0-9a-f]{32}:[1-9][0-9]{0,19}")
WORKSPACE_RE = re.compile(r"[1-9][0-9]{0,9}|r[-+]1|(?:special|name):[A-Za-z0-9_-]{1,70}")
ACTIONS = {
    "launch": (("--app-id", APP_ID_RE),),
    "focus-workspace": (("--workspace", WORKSPACE_RE),),
    "toggle-special": (("--workspace", WORKSPACE_RE),),
    "move-window": (("--identifier", WINDOW_RE), ("--workspace", WORKSPACE_RE)),
    "focus": (("--identifier", WINDOW_RE),),
    "close": (("--identifier", WINDOW_RE),),
    "toggle-floating": (("--identifier", WINDOW_RE),),
    "toggle-pin": (("--identifier", WINDOW_RE),),
}


def request(arguments: list[str]) -> dict:
    action = arguments[0] if arguments else ""
    fields = ACTIONS.get(action)
    if fields is None or len(arguments) != 1 + 2 * len(fields):
        raise ValueError("Invalid desktop action arguments")
    for (flag, pattern), actual, value in zip(fields, arguments[1::2], arguments[2::2]):
        if flag != actual or pattern.fullmatch(value) is None:
            raise ValueError(f"{flag} must be a literal desktop identifier")
    return call_json_with_stdin_binary(
        "/usr/local/bin/cos",
        ["__desktop", *arguments],
        b"",
        deadline_unix_ms=time.time_ns() // 1_000_000 + (45_000 if action == "launch" else 9_000),
    )


def main(arguments: list[str]) -> int:
    try:
        result = request(arguments)
    except (ValueError, KernelDenied, KernelUnavailable) as error:
        print(encode_wire_json({"ok": False, "error": str(error)}))
        return 1
    print(encode_wire_json({"ok": True, "result": result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
