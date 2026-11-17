"""Send a human desktop launch intent through the authenticated OS service."""

import json
import re
import sys
import time

from claw_os_sdk.kernel import (
    KernelDenied,
    KernelUnavailable,
    call_json_with_stdin_binary,
)


APP_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}")


def launch(app_id: str) -> dict:
    if not isinstance(app_id, str) or APP_ID_RE.fullmatch(app_id) is None:
        raise ValueError("A desktop launch requires one exact desktop AppID")
    return call_json_with_stdin_binary(
        "/usr/local/bin/cos",
        ["__desktop", "launch", "--app-id", app_id],
        b"",
        deadline_unix_ms=time.time_ns() // 1_000_000 + 45_000,
    )


def main(arguments: list[str]) -> int:
    try:
        if len(arguments) != 1:
            raise ValueError("A desktop launch requires one exact desktop AppID")
        result = launch(arguments[0])
    except (ValueError, KernelDenied, KernelUnavailable) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 1
    print(json.dumps({"ok": True, "result": result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
