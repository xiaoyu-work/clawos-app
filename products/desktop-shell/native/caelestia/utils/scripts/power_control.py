"""Send one confirmed action to the existing Claw OS power service."""

import sys
import time

from claw_os_sdk.kernel import KernelDenied, KernelUnavailable, call_json_with_stdin_binary


def main(args: list[str]) -> int:
    if len(args) != 1 or args[0] not in ("poweroff", "reboot", "hibernate", "suspend", "suspend-then-hibernate"):
        return 2
    try:
        reply = call_json_with_stdin_binary(
            "/usr/local/bin/cos", ["__power", args[0], "--confirm"], b"",
            deadline_unix_ms=time.time_ns() // 1_000_000 + 35_000,
        )
    except (KernelDenied, KernelUnavailable):
        return 1
    if reply.get("action") != args[0] or reply.get("requested") is not True:
        return 1
    print("requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
