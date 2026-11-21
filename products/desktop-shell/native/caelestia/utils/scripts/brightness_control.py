"""Use the OS display service instead of opening hardware devices."""

import json
import re
import sys
import time

from claw_os_sdk.kernel import KernelDenied, KernelUnavailable, call_json_with_stdin_binary


def main(args: list[str]) -> int:
    if args == ["status"]:
        command = args
    elif (
        len(args) == 3 and args[0] == "brightness"
        and re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}", args[1])
        and re.fullmatch(r"[1-9][0-9]?|100", args[2])
    ):
        command = [args[0], "--backlight", args[1], "--percent", args[2]]
    else:
        return 2
    try:
        reply = call_json_with_stdin_binary(
            "/usr/local/bin/yu", ["__display", *command], b"",
            deadline_unix_ms=time.time_ns() // 1_000_000 + 35_000,
        )
    except (KernelDenied, KernelUnavailable):
        return 1
    print(json.dumps(reply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
