"""Request one OS-reviewed launch of the selected desktop AppID."""

import json
import re
import sys
import time

from claw_os_sdk.kernel import KernelDenied, KernelUnavailable, call_json_with_stdin_binary


def emit(**fields) -> None:
    print(json.dumps(fields), flush=True)


def call(*args: str) -> dict:
    return call_json_with_stdin_binary(
        "/usr/local/bin/cos", ["__desktop-menu", *args], b"",
        deadline_unix_ms=time.time_ns() // 1_000_000 + 8_000,
    )


def main(args: list[str]) -> int:
    if len(args) != 1 or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}", args[0]) is None:
        emit(error="Invalid desktop AppID.")
        return 2
    try:
        result = call("request", args[0])
        review = result.get("review_id")
        if result.get("status") != "pending" or not isinstance(review, str) or re.fullmatch(r"ap-[0-9a-f]{12}", review) is None:
            emit(error="The OS did not return a launch review.")
            return 1
        emit(review_id=review)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            time.sleep(1)
            status = call("complete", review).get("status")
            if status == "submitted":
                emit(submitted=True)
                return 0
            if status != "pending":
                emit(error="The launch was not approved or the review expired.")
                return 1
        call("cancel", review)
        emit(error="The desktop launch review expired.")
    except (KernelDenied, KernelUnavailable) as error:
        emit(error=str(error))
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
