"""Submit an explicit desktop-menu action to the OS."""

import json
import re
import sys
import time

from claw_os_sdk.kernel import KernelDenied, KernelUnavailable, call_json_with_stdin_binary


def emit(**fields) -> None:
    print(json.dumps(fields), flush=True)


def call(command: str, *args: str) -> dict:
    timeout_ms = 15_000 if command == "__desktop-power" else 8_000
    return call_json_with_stdin_binary(
        "/usr/local/bin/yu", [command, *args], b"",
        deadline_unix_ms=time.time_ns() // 1_000_000 + timeout_ms,
    )


def main(args: list[str]) -> int:
    if len(args) != 2:
        emit(error="Expected one desktop action.")
        return 2
    kind, selection = args
    if kind in ("launch", "activate") and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}", selection):
        command = "__desktop-menu"
    elif kind == "power" and selection in ("poweroff", "reboot", "suspend", "hibernate", "suspend-then-hibernate"):
        command = "__desktop-power"
    else:
        emit(error="Invalid desktop action.")
        return 2
    try:
        if call(command, "activate" if kind == "activate" else "run", selection).get("status") == "submitted":
            emit(submitted=True)
            return 0
        emit(error="The OS did not confirm the requested action.")
    except (KernelDenied, KernelUnavailable) as error:
        emit(error=str(error))
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
