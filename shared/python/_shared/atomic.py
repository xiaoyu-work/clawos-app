"""Atomic file-write helpers for sidecar metadata and small payloads.

``atomic_write_bytes`` replaces its destination. ``atomic_create_bytes``
instead links a fully synced temporary inode into a previously unused path and
fails if that path already exists. Neither exposes a half-written file to a
concurrent reader.

Replacement sequence:

1. write to ``<path>.tmp.<pid>.<uuid>``
2. ``fsync`` the temp fd so the contents hit stable storage
3. ``os.replace(tmp, path)`` (atomic on the same filesystem)
4. ``fsync`` the parent directory so the rename itself is durable

On a crash between step 1 and step 3, the temp file is orphaned but
the original path is intact.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any


def _fsync_dir(path: str, *, strict: bool = False) -> None:
    """``fsync`` the directory at ``path``.

    Legacy callers are best-effort. Strict callers receive every open/fsync
    failure, including failures after replacement may already have occurred.
    """
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    if strict:
        flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except (OSError, ValueError):
        if strict:
            raise
        return
    try:
        try:
            os.fsync(fd)
        except OSError:
            if strict:
                raise
    finally:
        os.close(fd)


def atomic_write_bytes(
    path: str, data: bytes, mode: int = 0o644, *, strict: bool = False
) -> None:
    """Atomically replace ``path`` with ``data``.

    Creates parent directories on demand. ``mode`` is applied to the
    temp file before the rename so a concurrent ``open`` after the
    rename sees the intended mode. Strict writes require durable fsyncs and
    exclusive no-follow staging; a failure after replacement is indeterminate.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError(f"data must be bytes-like, got {type(data).__name__}")
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
    flags = os.O_WRONLY | os.O_CREAT
    flags |= (os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)) if strict else os.O_TRUNC
    fd = os.open(tmp, flags, mode)
    try:
        with os.fdopen(fd, "wb", closefd=True) as f:
            f.write(bytes(data))
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                if strict:
                    raise
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    try:
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _fsync_dir(parent, strict=strict)


def atomic_create_bytes(path: str, data: bytes, mode: int = 0o644) -> None:
    """Atomically create ``path`` without replacing an existing entry."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError(f"data must be bytes-like, got {type(data).__name__}")
    parent = os.path.dirname(path) or "."
    tmp = f"{path}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb", closefd=True) as file:
            file.write(bytes(data))
            file.flush()
            os.fsync(file.fileno())
        os.link(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    os.unlink(tmp)
    _fsync_dir(parent)


def atomic_write_text(path: str, text: str, mode: int = 0o644, encoding: str = "utf-8") -> None:
    """Atomically replace ``path`` with ``text`` encoded as UTF-8."""
    atomic_write_bytes(path, text.encode(encoding), mode=mode)


def atomic_write_json(
    path: str, obj: Any, *, indent: int = 2, mode: int = 0o644, strict: bool = False
) -> None:
    """Atomically replace ``path`` with ``json.dumps(obj)`` bytes."""
    payload = json.dumps(obj, indent=indent, ensure_ascii=False).encode("utf-8")
    atomic_write_bytes(path, payload, mode=mode, strict=strict)
