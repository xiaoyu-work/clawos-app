"""Use the OS audio service without connecting to the user's sound server."""

import json
import re
import sys
import time

from claw_os_sdk.kernel import KernelDenied, KernelUnavailable, call_json_with_stdin_binary


def main(args: list[str]) -> int:
    if not args:
        return 2
    action, *fields = args
    if action == "status":
        valid = not fields
    elif action in ("output-default", "input-default"):
        valid = len(fields) == 2 and fields[0] == "--target" and re.fullmatch(r"[1-9][0-9]{0,9}", fields[1])
    elif action in ("output-volume", "input-volume"):
        valid = len(fields) == 2 and fields[0] == "--value" and re.fullmatch(r"[0-9]{1,3}", fields[1])
    elif action in ("output-mute", "input-mute"):
        valid = len(fields) == 2 and fields[0] == "--value" and fields[1] in ("on", "off")
    else:
        valid = False
    if not valid:
        return 2
    try:
        reply = call_json_with_stdin_binary(
            "/usr/local/bin/cos", ["__audio", *args], b"",
            deadline_unix_ms=time.time_ns() // 1_000_000 + 35_000,
        )
    except (KernelDenied, KernelUnavailable):
        return 1
    print(json.dumps(reply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
