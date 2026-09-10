"""Shared helpers for the gateway apps.

Gateway clients import :mod:`gateway._shared` from the common Python root
(``shared/python`` in development, ``/usr/lib/cos/python`` when installed).
Every gateway should reach for the helpers
here before rolling its own. The goal is to give each gateway a tiny,
audited blast radius:

* :mod:`safe_egress`   — outbound HTTP that consults ``policy.require``,
                          rejects RFC1918 / loopback / link-local hosts,
                          and refuses to follow 30x redirects (so a
                          server can't bounce us to ``169.254.169.254``).
* :mod:`safe_subprocess` — wraps :func:`subprocess.run` with mandatory
                          timeouts, scrubbed environments, and
                          ``stdin=DEVNULL`` so a hung helper can never
                          pin the gateway forever or inherit ambient
                          credentials.
* :mod:`inbound`       — sender allowlists, in-process rate limiters,
                          and HMAC signature verification helpers for
                          gateways that accept inbound traffic.
* :mod:`atomic`        — ``tmp + fsync + replace + fsync(parent)``
                          atomic file writes for gateway state files
                          (JSONL offsets, PID files, etc).
* :mod:`websocket`     — stdlib-only RFC 6455 client layered on the
                          same policy-gated, DNS-pinned egress path.

These libraries are staged once by the App-owned common runtime. They do not
include App entrypoints or the OS SDK/runtime authority they consume.
"""

from __future__ import annotations

__all__ = [
    "safe_egress",
    "safe_subprocess",
    "inbound",
    "atomic",
    "gateway_memory",
    "websocket",
]
