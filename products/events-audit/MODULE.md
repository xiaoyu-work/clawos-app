# Events and Audit Product

Own `event-center`'s status/recent/watch-pid MCP tools. The assigned `log` App
awaits its separate migration; grouping does not merge event and audit authority.

| Path | Responsibility |
| --- | --- |
| `apps/event-center/app.json` | Sensitive `sys.events:observe` grant and bounded-query argument contract |
| `apps/event-center/main.py` | Limit/source/PID validation and typed `cos __events` requests |
| `apps/event-center/server.py` | Direct SDK MCP handlers |
| `apps/event-center/test_main.py` | Direct/SDK routing, defaults, bounds, scopes and broker errors |
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

```bash
python3 tools/test.py events-audit
python3 tools/stage.py events-audit --root build/events-audit-stage
```

Tests use synthetic broker replies; they do not read real events or register PID watches.
