"""Request the protected lock for this GUI's own desktop."""

import time

from claw_os_sdk.kernel import KernelDenied, KernelUnavailable, call_json_with_stdin_binary


def main() -> int:
    try:
        reply = call_json_with_stdin_binary(
            "/usr/local/bin/cos", ["__desktop-lock"], b"",
            deadline_unix_ms=time.time_ns() // 1_000_000 + 10_000,
        )
    except (KernelDenied, KernelUnavailable):
        return 1
    return 0 if reply.get("locked") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
