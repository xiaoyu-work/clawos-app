# Calendar Product

Own Calendar's local event operations, Google/Outlook integration, MCP
entrypoint, manifest and tests. The system Agent coordinates cross-product
work; Calendar never calls another App.

| Path | Responsibility |
| --- | --- |
| `apps/calendar/app.json` | Existing identity, provider choices and per-provider authority |
| `apps/calendar/main.py` | Local SQLite events and remote provider operations |
| `apps/calendar/server.py` | MCP transport over the same implementation |
| `apps/calendar/test_main.py` | Local event and provider behavior |
| `package.json` | Product-owned installation and additional test inputs |

The source move preserves the installed `calendar` identity, data paths and
grants. The OS retains worker isolation, data-partition migration, policy,
credentials and shared libraries. `panel-calendar` has not moved yet; this
source split does not claim UI/backend consolidation.

From the repository root:

```bash
python3 tools/test.py calendar
python3 tools/stage.py calendar --root build/calendar-stage
```
