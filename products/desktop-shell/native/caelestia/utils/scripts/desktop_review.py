"""Request a single desktop effect through the OS review window."""

import json
import re
import sys
import time

from claw_os_sdk.kernel import KernelDenied, KernelUnavailable, call_json_with_stdin_binary


def emit(**fields) -> None:
    print(json.dumps(fields), flush=True)


def call(command: str, *args: str) -> dict:
    timeout_ms = 15_000 if command == "__desktop-power" and args[0] == "complete" else 8_000
    return call_json_with_stdin_binary(
        "/usr/local/bin/cos", [command, *args], b"",
        deadline_unix_ms=time.time_ns() // 1_000_000 + timeout_ms,
    )


def main(args: list[str]) -> int:
    if len(args) != 2:
        emit(error="Expected one desktop review selection.")
        return 2
    kind, selection = args
    if kind == "launch" and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}", selection):
        command = "__desktop-menu"
    elif kind == "power" and selection in ("poweroff", "reboot", "suspend", "hibernate", "suspend-then-hibernate"):
        command = "__desktop-power"
    else:
        emit(error="Invalid desktop review selection.")
        return 2
    try:
        result = call(command, "request", selection)
        review = result.get("review_id")
        if result.get("status") != "pending" or not isinstance(review, str) or re.fullmatch(r"ap-[0-9a-f]{12}", review) is None:
            emit(error="The OS did not return a review.")
            return 1
        emit(review_id=review)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            time.sleep(1)
            status = call(command, "complete", review).get("status")
            if status == "submitted":
                emit(submitted=True)
                return 0
            if status != "pending":
                emit(error="The action was not approved or the review expired.")
                return 1
        call(command, "cancel", review)
        emit(error="The desktop review expired.")
    except (KernelDenied, KernelUnavailable) as error:
        emit(error=str(error))
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
