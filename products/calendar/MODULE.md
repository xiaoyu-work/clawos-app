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
| `apps/panel-calendar/` | Unchanged shell launcher, manifest and named Calendar read grant |
| `native/claw-applet-calendar/` | Complete monthly picker, popup, selected-day agenda, translations, icon and desktop entry |
| `native/build.py`, `native/Cargo.lock`, `native/patches.toml` | Independent native build/test against the locked OS toolkit |
| `PROVENANCE.md`, `native/LICENSE` | Native source origin and preserved GPL terms |
| `package.json` | Product-owned installation and additional test inputs |

The source move preserves the installed `calendar` identity, data paths and
grants. The OS retains worker isolation, data-partition migration, policy,
credentials and shared libraries. `panel-calendar` is a product-owned library
hosted by `cosmic-applets`; its `AgendaProvider` interface receives selected
dates and returns typed events/errors. The OS shell injects the existing
read-only, `data.db.read:Name(calendar)` provider, also used by Widget Rail.
This source split does not merge the Calendar and panel identities or data.

From the repository root:

```bash
python3 tools/test.py calendar
python3 tools/stage.py calendar --root build/calendar-stage
python3 products/calendar/native/build.py test
```

The native command prepares only immutable toolkit sources, generates build
inputs under `build/calendar-native`, and compiles with the checked-in lock.
`tools/stage_native.py calendar --root <empty-build-input-directory>` exports
the library and license for OS composition. Native tests cover selected-day
provider injection, stale generations, queued refreshes and visible denial.
