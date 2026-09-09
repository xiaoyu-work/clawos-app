"""Notify intent and validation; durable state belongs to the OS service."""

from __future__ import annotations

import unicodedata

from client import request


def send(message: str, urgent: bool = False) -> dict[str, object]:
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must be a non-empty string")
    if len(message) > 4000:
        raise ValueError("message must contain at most 4000 characters")
    if any(unicodedata.category(ch) == "Cc" and ch not in "\n\r\t" for ch in message):
        raise ValueError("message contains unsupported control characters")
    message.encode("utf-8")
    if type(urgent) is not bool:
        raise ValueError("urgent must be a boolean")
    return request({"action": "send", "message": message, "urgent": urgent})


def list_notifications(limit: int = 20) -> dict[str, object]:
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ValueError("limit must be an integer")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be 1..100")
    return request({"action": "list", "limit": limit})
