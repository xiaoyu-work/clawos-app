# Events and Audit Product

Own `event-center`'s three MCP tools and `log`'s four legacy activity-log tools.
Both assigned App sources have moved; system audit-service integration is
still pending and grouping does not merge event and audit authority.

| Path | Responsibility |
| --- | --- |
| `apps/event-center/app.json` | Sensitive `sys.events:observe` grant and bounded-query argument contract |
| `apps/event-center/main.py` | Limit/source/PID validation and typed `cos __events` requests |
| `apps/event-center/server.py` | Direct SDK MCP handlers |
| `apps/event-center/test_main.py` | Direct/SDK routing, defaults, bounds, scopes and broker errors |
| `apps/log/` | Legacy JSONL read/tail/search/manual-write implementation and isolated direct/SDK tests |
| `package.json` | Product-owned staging and test inputs |

Preserve the installed `event-center` identity and existing event observation
authority. Recent queries default to 100 records, accept 1..1000, and optionally
filter udev/systemd/journal/storage/security/process. Watching a PID accepts a
positive 32-bit integer; the OS validates the live process and owns pidfd lifetime,
deduplication and the watch limit.

The OS owns background udev/systemd/journal subscriptions, event persistence,
source health and process-exit publication. This App is a typed service client,
not another watcher or event database. Audit, context-event and notification
stores retain their own boundaries. No state is copied or reset by relocation,
and Apps do not invoke other Apps.

`log` retains separate `data.log.read` and `data.log.write` Wild grants. Read is
newest-first, tail is chronological and search preserves stored order; manual
entries keep `source=user`. Unlike `event-center`, this is not a broker client:
it directly uses `COS_DATA_DIR/logs/audit.jsonl` (fallback `/var/lib/cos`).
The App Host supplies an isolated data directory, so the filename and legacy
manifest description do not prove access to the OS's authoritative audit trail.
Do not mount the system audit file writable or append these unchained manual
entries to it. A typed, owner-scoped audit service and explicit manual-entry
semantics are pending; the OS retains audit integrity and persistence authority.
This source move preserves the existing file layout and copies no runtime logs.

```bash
python3 tools/test.py events-audit
python3 tools/stage.py events-audit --root build/events-audit-stage
```

Tests use synthetic broker replies and temporary JSONL files; they do not read
real audit/events or register PID watches.
