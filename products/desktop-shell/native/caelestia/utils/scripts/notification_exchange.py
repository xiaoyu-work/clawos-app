"""Use the common Host's notification presentation resource."""

import json
import sys
import time

from claw_os_sdk.kernel import KernelDenied, KernelUnavailable, call_json_with_stdin_binary


def main() -> int:
    limit = 768 * 1024
    data = sys.stdin.buffer.read(limit + 1)
    if len(data) > limit:
        return 1
    try:
        reply = call_json_with_stdin_binary(
            "/usr/local/bin/yu",
            ["__gui_notifications", "--request-stdin"],
            data,
            deadline_unix_ms=time.time_ns() // 1_000_000 + 5_000,
        )
    except (KernelDenied, KernelUnavailable):
        return 1
    print(json.dumps(reply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
