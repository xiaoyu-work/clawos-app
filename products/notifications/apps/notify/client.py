"""Shared installed-SDK client; identity and policy are enforced by clawd."""

from __future__ import annotations

import json
import time

from claw_os_sdk import kernel
from claw_os_sdk.mcp import current_context


def request(intent: dict[str, object]) -> dict[str, object]:
    context = current_context()
    context.raise_if_cancelled()
    deadline = time.time_ns() // 1_000_000 + 5000
    if context.deadline_unix_ms is not None:
        deadline = min(deadline, context.deadline_unix_ms)
    return kernel.call_json_with_stdin_binary(
        "/usr/local/bin/cos",
        ["__notifications", "request", "--request-stdin", "--deadline", str(deadline)],
        json.dumps(intent, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        deadline_unix_ms=deadline,
        check_cancelled=context.raise_if_cancelled,
    )
