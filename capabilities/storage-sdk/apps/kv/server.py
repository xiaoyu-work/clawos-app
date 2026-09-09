"""kv — persistent string key-value MCP service.

The service caches unchanged store snapshots across calls. Mutations
reload the latest committed snapshot under an exclusive file lock.

The kernel runs the cap check before forwarding any `tools/call` to
us (using `app.json`'s `mcp.tools[].needs[]`), so handlers here
don't repeat `policy.require` — they trust the bridge to have gated
the call already.
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import fnmatch
import json
import os
import threading

from _shared.atomic import atomic_write_bytes
from claw_os_sdk.mcp import App

DATA_DIR = os.environ.get("COS_DATA_DIR", "/var/lib/cos")
STORE_PATH = os.path.join(DATA_DIR, "kv.json")
LOCK_PATH = STORE_PATH + ".lock"

app = App.from_manifest()


_cache: dict[str, str] | None = None
_cache_bytes: bytes | None = None
_cache_lock = threading.RLock()


@contextmanager
def _store_lock(mode: int):
    os.makedirs(DATA_DIR, exist_ok=True)
    fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a+b") as lock_fd:
        fcntl.flock(lock_fd, mode)
        try:
            yield
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def _load_locked() -> dict[str, str]:
    global _cache, _cache_bytes
    try:
        with open(STORE_PATH, "rb") as file:
            contents = file.read()
    except FileNotFoundError:
        _cache = {}
        _cache_bytes = None
        return _cache
    if _cache is not None and contents == _cache_bytes:
        return _cache
    loaded: object = json.loads(contents.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("kv store must contain a JSON object")
    data: dict[str, str] = {}
    for key, value in loaded.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("kv store must contain only string keys and values")
        data[key] = value
    _cache, _cache_bytes = data, contents
    return _cache


def _load() -> dict[str, str]:
    global _cache, _cache_bytes
    with _cache_lock:
        try:
            os.stat(STORE_PATH)
        except FileNotFoundError:
            _cache = {}
            _cache_bytes = None
            return _cache
        with _store_lock(fcntl.LOCK_SH):
            return _load_locked()


def _save_locked(data: dict[str, str]) -> None:
    """Publish a new cache snapshot only after its private atomic commit."""
    global _cache, _cache_bytes
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    atomic_write_bytes(STORE_PATH, payload, mode=0o600)
    _cache, _cache_bytes = data, payload


@app.tool("kv.get")
def kv_get(key: str) -> str:
    return _load().get(key, "")


@app.tool("kv.set")
def kv_set(key: str, value: str) -> dict:
    with _cache_lock, _store_lock(fcntl.LOCK_EX):
        data = dict(_load_locked())
        data[key] = value
        _save_locked(data)
    return {"key": key, "value": value}


@app.tool("kv.del")
def kv_del(key: str) -> dict:
    with _cache_lock:
        if key not in _load():
            return {"key": key, "deleted": False}
        with _store_lock(fcntl.LOCK_EX):
            data = dict(_load_locked())
            existed = key in data
            if existed:
                del data[key]
                _save_locked(data)
    return {"key": key, "deleted": existed}


@app.tool("kv.list")
def kv_list(pattern: str = "*") -> dict:
    data = _load()
    keys = sorted(k for k in data if fnmatch.fnmatch(k, pattern))
    return {"pattern": pattern, "keys": keys}


@app.tool("kv.dump")
def kv_dump() -> dict:
    data = _load()
    return {"count": len(data), "data": dict(data)}


if __name__ == "__main__":
    app.serve()
