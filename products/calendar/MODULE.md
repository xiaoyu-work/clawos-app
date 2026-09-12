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
| `apps/panel-calendar/` | Standalone native launcher, unchanged manifest and named Calendar read grant |
| `native/claw-applet-calendar/` | Complete monthly picker, popup, selected-day agenda, translations, icon and desktop entry |
| `native/claw-applet-calendar/src/main.rs`, `src/service.rs` | Independent binary entry and public OS SDK agenda client |
| `native/claw-applet-calendar/build.rs`, `justfile` | Product-owned localized desktop generation and native installation |
| `native/build.py`, `native/Cargo.lock`, `../../tools/native_build.py` | Locked standalone native build/test against declared SDK/toolkit inputs |
| `PROVENANCE.md`, `native/LICENSE` | Native source origin and preserved GPL terms |
| `package.json` | Product-owned installation and additional test inputs |

The source move preserves the installed `calendar` identity, data paths and
grants. The OS retains the SDK/runtime, worker isolation, data-partition
migration, policy and credential authority. App-owned support comes from
[`shared/python`](../../shared/python). `panel-calendar` launches
`/usr/bin/claw-applet-calendar`, not `cosmic-applets`.
The binary retains the existing UI and internal `AgendaProvider` seam; its
production callback uses `claw_os_sdk::applet::Client` and the fixed OS helper.
The existing read-only `data.db.read:Name(calendar)` provider stays OS-owned,
also serving Widget Rail. Denial and missing/broken service errors remain
visible. No identity, grant or data partition is merged.

The OS App-service Host now binds Calendar's existing owner/App data partition
through a private UID-mapped view, so a new service Host can read the same
on-disk state without copying it or changing its owner. This is not a new
Calendar directory. The panel still needs the OS-owned cross-App resource
binding; its own private data directory is not Calendar's database. Legacy
task-host operations and installed GUI/resource acceptance remain separate.

The Rust UI uses the same verified App manifest, identity/session, capability
and sandbox contract as any other App. Neither its language nor its package
origin grants privilege. The public data service is available to other Apps
with the same resource scopes; no native App allowlist entry is added.

From the repository root:

```bash
python3 tools/test.py calendar
python3 tools/stage.py calendar --root build/calendar-stage
python3 products/calendar/native/build.py test
```

The native command prepares declared immutable SDK/toolkit inputs, generates
build inputs under `build/calendar-native`, and uses `build/native-target`
unless `--target-dir` is supplied. It compiles the library and actual standalone
ELF with the checked-in lock.
`tools/stage_native.py calendar --root <empty-build-input-directory>` exports
native build inputs, not installed binaries. The product's `just install`
installs the compiled binary, generated `com.clawos.PanelCalendarButton.desktop`
and original scalable Calendar icon. Its `rootdir`, `prefix`, `targetdir` and
`debug` parameters follow the original applet installer style.
Installation is build-time staging and requires an explicit non-root `rootdir`.
It installs files only, not permissions or installed-system hooks.

The independent native App package requires `claw-os-applet-services-v1 (= 1)`;
the OS shell neither links this UI nor generates its resources. Native tests
retain selected-day injection, stale generations, queued refreshes and visible
denial, and execute the actual standalone binary headlessly. This is not a
claim of interactive Wayland acceptance.
