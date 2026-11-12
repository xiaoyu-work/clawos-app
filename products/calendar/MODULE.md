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
| `apps/panel-calendar/` | Existing native identity, manifest-bound GUI/MCP entry and unchanged named Calendar read grant |
| `native/claw-applet-calendar/` | Complete monthly picker, popup, selected-day agenda, translations, icon and desktop entry |
| `native/claw-applet-calendar/src/main.rs`, `src/service.rs`, `src/mcp.rs` | MCP-first binary entry and shared read-only public OS SDK agenda client |
| `native/claw-applet-calendar/build.rs`, `justfile` | Product-owned localized desktop generation and native installation |
| `native/build.py`, `native/Cargo.lock`, `../../tools/native_build.py` | Locked standalone native build/test against declared SDK/toolkit inputs |
| `PROVENANCE.md`, `native/LICENSE` | Native source origin and preserved GPL terms |
| `package.json` | Product-owned installation and additional test inputs |

The source move preserves the installed `calendar` identity, data paths and
grants. The OS retains the SDK/runtime, worker isolation, data-partition
migration, policy and credential authority. App-owned support comes from
[`shared/python`](../../shared/python). `panel-calendar` selects the same real
`bin/claw-applet-calendar` ELF for GUI and lazy stdio MCP. The compatibility
command is exported through the common Host, not `cosmic-applets`.
The binary retains the existing UI and internal `AgendaProvider` seam. Both
surfaces use the published SDK 0.2.1 generic wire client with the fixed
`/usr/local/bin/cos __calendar day <year> <month> <day>` OS command and SDK
`CalendarEvent` records. No Desktop-only applet-provider, other App, raw
database, user bus or process-global credential override is used.
The existing read-only `data.db.read:Name(calendar)` provider stays OS-owned,
also serving Widget Rail. Denial and missing/broken service errors remain
visible. No identity, grant or data partition is merged.

The OS service and ordinary task-operation Hosts bind Calendar's existing
owner/App data partition through private UID-mapped views, so a new Host can read the same
on-disk state without copying it or changing its owner. This is not a new
Calendar directory. Panel and Widget Rail reads now use the owner-scoped OS
Calendar service through the public SDK wire interface. Their own data directories
cannot select the Calendar database, and they receive no raw file access.
Installed GUI/resource acceptance remains separate.

## Read-only panel service and Web UI

`panel-calendar.day` accepts one canonical `date` (`YYYY-MM-DD`) and returns
`{date, events}` with the existing `id`, `title`, `start`, nullable `end` and
`location` fields. Its only need is `data.db.read:Name(calendar)`, exactly the
original panel grant; it does not inherit Calendar's provider credentials or
write permissions. Calls are bounded and cancellation/deadlines drop the SDK
CLI future. The OS still authenticates owner/session and authorizes the read.

The owning Web page selects a read-only day picker/agenda for `panel-calendar`;
the separate `calendar` identity retains its existing CRUD, provider and
invitation UI. Denial, missing services and invalid service data are visible,
not empty agendas. The native UI continues to run independently of MCP or an
active Agent/model. MCP dispatch precedes GUI initialization and the existing
direct `--version` handling; other native arguments retain their ignored behavior.

The coordinated 0.2.1 `desktop.needs` requests the Calendar read and a separate
high-risk `ui.panel` capability for the native panel surface. That authority
requires protected owner approval; neither panel metadata nor Calendar access
grants it. The read-only MCP tool never requests or inherits `ui.panel`.
The standalone GUI explicitly creates one ordinary top-right Layer Shell
surface through the published toolkit, using the original applet's icon/padding
geometry and no keyboard interactivity. It suppresses the toolkit's default
XDG main window; the original picker/agenda popup and SDK reader are unchanged.
No panel environment, OS shell embedding, user bus or App-name entitlement
supplies Layer Shell authority. Real panel pixels/lifetime and an interacted
popup/Calendar-service read remain distinct acceptance gates.

The Rust UI uses the same verified App manifest, identity/session, capability
and sandbox contract as any other App. Neither its language nor its package
origin grants privilege. The public data service is available to other Apps
with the same resource scopes; no native App allowlist entry is added.

## Activity event objects

The `local-event`, `google-event` and `outlook-event` types fix the provider
in their declaration. Each resolver takes only `--id`, checks its existing
provider-specific grants and returns a canonical App reference. Local
resolution opens an existing database read-only and never creates a missing
store. Remote IDs are encoded as individual API path segments.
List/create/update results carry the same references without renaming the
App, copying account data or treating an object reference as permission.

## Provider invitations and responses

Successful mutations publish owner-bound `app:calendar` events through the
public SDK and exact named IPC grant. References remain reported data; an
event does not prove guest delivery or supply task authority. Publication
failures preserve the original result without repeating the calendar effect.

`invite` explicitly creates a Google/Outlook meeting with 1..100 distinct
attendee addresses and requests provider delivery. `respond` accepts,
tentatively accepts or declines as the authorized calendar owner. Both require
explicit confirmation before App policy checks; confirmation is not OS consent.
Google responses change only the `self` attendee and use the returned ETag
for conditional patching. Outlook uses its dedicated response actions.
Times require offsets; Outlook receives explicit UTC date/time values.
Local event CRUD is unchanged and does not pretend to deliver invitations.
Returned notification fields report requested delivery, not guest receipt.

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
The `native_payload` declaration prepares the real package-local ELF with the
original installer resources and GPL license; source staging does not create
a substitute binary or signed payload.
`tools/stage_native.py calendar --root <empty-build-input-directory>` exports
native build inputs, not installed binaries. The product's `just install`
installs the compiled binary, generated `com.clawos.PanelCalendarButton.desktop`
and original scalable Calendar icon. Its `rootdir`, `prefix`, `targetdir` and
`debug` parameters follow the original applet installer style.
Installation is build-time staging and requires an explicit non-root `rootdir`.
It installs files only, not permissions or installed-system hooks.

The binary no longer depends on `claw-os-applet-provider`; shared release
metadata requires the Agent-provided `claw-os-calendar-read-v1 (= 1)` interface,
not the Desktop-only applet provider. The OS shell
neither links this UI nor generates its resources. Native tests
retain selected-day injection, stale generations, queued refreshes and visible
denial, exercise synthetic public CLI/MCP reads and execute the actual standalone
binary headlessly. These fixtures never access real accounts or services. This is not a
claim of interactive Wayland acceptance.
