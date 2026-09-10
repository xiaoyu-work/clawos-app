"""App-owned helpers imported from the common Python library root.

Development uses ``shared/python``; installed Apps use
``/usr/lib/cos/python``. Both expose the same imports::

    from _shared.paths import safe_realpath
    from _shared.atomic import atomic_write_bytes, atomic_write_json
    from _shared.env_scrub import scrub_env

Policy, broker, credential and AI authority remain in the OS SDK/runtime.
"""
