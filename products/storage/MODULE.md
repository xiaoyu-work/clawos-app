# Storage Product

Own `storage-manager`'s six MCP tools for inventory, health, read-only
filesystem checks, mounting, unmounting and ejecting devices.

| Path | Responsibility |
| --- | --- |
| `apps/storage-manager/app.json` | Separate observation, diagnosis and exact device mount scopes |
| `apps/storage-manager/main.py` | Canonical device validation and `cos __storage` requests |
| `apps/storage-manager/server.py` | Direct SDK MCP handlers |
| `apps/storage-manager/test_main.py` | Device validation, error/timeout handling and all SDK routes |
| `package.json` | Product-owned staging and test inputs |

Preserve the installed `storage-manager` identity. The OS provider owns block
device verification, session-bound UDisks2 execution, operation serialization,
SMART diagnostics and offline no-repair filesystem checking.

Observation uses `sys.observe` scope `storage`, health/check use `sys.storage`
scope `diagnose`, and mount/unmount/eject use the exact canonical device path
under `sys.mount`. No format/repair operation or new confirmation parameter
is introduced. Source relocation does not move mounted data or give the App
access to other products' databases.

```bash
python3 tools/test.py storage
python3 tools/stage.py storage --root build/storage-stage
```

Tests use synthetic device/broker responses and never operate on live storage.
