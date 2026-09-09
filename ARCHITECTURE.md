# Application Architecture

`clawos-app` owns independently developed application products. `claw-os`
owns the system Agent, privileged broker, runtime authority, SDK and OS image.

```text
Product UI ----+
              +--> product business implementation --> versioned OS SDK/runtime
Product MCP --+                                             |
                                                       clawd / AI gate
```

Applications do not call one another. One product can have multiple entry
points without duplicating its account state or inheriting a union of grants.

| Surface | Owner |
| --- | --- |
| `products/mail/` | Thunderbird source, Mail AI, legacy email and restricted delivery, extension UI and product packaging |
| `products/calendar/` | Local events, Google/Outlook integration, Calendar MCP and the complete native panel UI library/assets |
| `products/files/` | Complete native Files UI/library/companion, filesystem MCP, owner-scoped Recoll, shared document parsing and SDK AI |
| `products/browser/` | Search, headless browsing and attached-browser Apps, MV3 extension and Native Host; privileged provider and native engine remain OS-owned |
| `products/terminal/` | Complete native Terminal UI/MCP/resources and command/script/background App operations; sandbox, snapshots and process authority remain OS-owned |
| `products/containers/` | Container-management App contract and typed broker client; privileged backend remains OS-owned |
| `products/backup-recovery/` | Data-backup and whole-system recovery App contracts; backend execution, credentials, mount authorization and snapshot index remain OS-owned |
| `products/store/` | Complete native Store UI/MCP/resources, shared package catalog and pkg contract; privileged transactions and installed state remain OS-owned |
| `products/diagnostics/` | Hardware, crash and network diagnostic App contracts; privileged collectors, crash data, DNS-pinned probes and per-domain authority remain OS-owned |
| `products/storage/` | Storage-management App contract; device validation, UDisks2 execution and read-only filesystem checkers remain OS-owned |
| `products/settings/` | Complete native Settings UI/workspace/MCP/resources plus eleven management Apps; system execution, credentials, account/queue state and twelve independent identities/grants remain separate |
| `products/security/` | Security inspection, firewall and USB App contracts with separate grants; collectors, nftables/sysfs/udev/UDisks2 execution, durable rules and owner-bound rollback remain OS-owned |
| `products/maintenance/` | Exact-path configuration and exact-unit service App contracts; validators, atomic writes, systemctl execution, mutation records and rollback remain OS-owned |
| `products/events-audit/` | Event service client and legacy JSONL activity App; event/audit authority remains OS-owned; `log` still needs typed audit-service integration rather than direct system-audit access |
| `products/launcher/` | Complete native Launcher UI and Python/native MCP surfaces sharing product catalog/search/recent and typed launch logic; desktop execution and native UI backend service stay OS-owned |
| `products/editor/` | Complete native Text Editor UI, seven MCP handlers and shared SDK AI presentation; controlled filesystem/snapshot, desktop and model-provider authority remain OS-owned |
| `products/capture/` | Complete native screenshot portal client, MCP and resources; interactive portal UI, session/capture authority and durable output remain OS-owned |
| `products/media-player/` | Complete native GStreamer UI/MPRIS/MCP/resources; live playback stays product-owned, and owner-bound observation/control authority stays OS-owned |
| `products/notifications/` | Complete native Layer Shell UI/MCP/config/util libraries and original build; owner/source-bound durable notification state and the single delivery consumer stay OS-owned |
| `products/clipboard/` | Selection App contract and complete native CopyQ history panel; separate selection/history grants, with policy and Wayland authority OS-owned |
| `products/notification-delivery/` | One-shot ntfy/Pushover/Webhook App sources; durable notification state, DND, delivery leases/retries and the separate Rust ntfy adapter/dispatcher remain OS-owned |
| `tools/stage.py` | Deterministic assembly of product-owned installed assets |
| `products/desktop-widgets/` | Complete Widget Rail native presentation and assets; Calendar/task/telemetry access and authority remain OS-provided |
| `products/home-integration/` | Home Assistant REST adapter source; external server, accounts, devices and automation state are not imported; OS credentials and egress authority remain separate |
| `products/messaging-channels/` | Discord/Telegram and outbound-only DingTalk/Google Chat/Lark/Matrix/Mattermost/Rocket.Chat/Signal/Slack/SMS/Teams/Webex/WhatsApp/Zulip connector sources; authenticated inbound owner/sender admission, lifecycle and durable replay handling remain pending |
| `platform.lock.json`, `tools/platform_dependency.py` | Immutable development SDK/runtime dependency, not a second OS implementation |
| `tools/test.py` | Product-scoped tests using the locked runtime |
| `claw-os` | Native authority launcher, package signing, installation, core services and system integration |

OS builds pin a commit of this repository and invoke the product asset builder.
The resulting assets enter the existing signed OS package; installed paths and
App provenance checks do not change. No installed system downloads a mutable
Git branch or silently substitutes an unverified App.

Mail preserves `mail-ai` and its six AI operations, plus the existing `email`
SMTP/Gmail/Outlook implementation. Native Thunderbird source is also owned
here, along with the restricted `gateway-email` delivery adapter. These source moves do not merge
legacy identities or account state; completing that product cutover requires
explicit account, consent and installation changes.

SDK/runtime development dependencies are fetched by immutable commit into
ignored build storage. Only those library source directories are checked out;
product code does not import operating-system implementation files. Published
runtime packages can replace this source dependency without changing the
product interface. The legacy email transport also uses the pinned
`apps/_shared` package and the sibling `canonical_argv.py` shared module
(included by the sparse checkout's parent directory). No other App's
implementation is checked out. OS package assembly already owns these
installed libraries. Delivery imports the distinct `gateway._shared` namespace
from its pinned shared library, rather than colliding with email's `_shared`.
Staging preserves nested App paths; joining their components with `-` must
produce the manifest ID, matching OS discovery.

Each product's `package.json` selects its installed Apps and additional tests.
The test runner includes each declared App's `test_main.py`, then only the
explicit extra tests; it never recursively collects a vendored source tree.
Calendar's event database and provider authority are unchanged by relocation.
OS integration tests consume the pinned product source to retain coverage of
real Calendar code crossing the broker and sandbox boundaries.

The native Calendar library accepts an `AgendaProvider` callback rather than
depending on another App. The OS shell links the library and injects its
shared read-only Calendar provider; policy checks remain before database
access. UI resources and build inputs are product-owned. Development checks
out only the locked shared `desktop/toolkit` source, including its iced tree,
into a separate native dependency cache. OS builds use their own forked
toolkit and immutable App source pin. The panel manifest and compiled shell
remain in `claw-os-desktop`; Calendar's Python backend remains in
`claw-os-agent`. Installed state, grants and signed APT updates do not change.

Clipboard's complete native popup, CopyQ implementation and resources use the
same native staging/build mechanism. Its `HistoryPolicy` callback asks the OS
host for read/write authorization on the named history scope before executing
CopyQ; authority is not imported from Widget Rail or copied into the product.
The human-only `panel-clipboard` identity and desktop package ownership remain
separate from `clipboard-manager` and its Wayland selection grants. Relocation
does not integrate the two backends or move user history.

`tools/native_build.py <product> test` is the shared native development/CI runner.
It uses each product's checked-in lock and the common toolkit patch mapping,
with generated inputs under `build/<product>-native` and a shared native target
cache. CI compiles and tests Calendar, Clipboard and Desktop Widgets libraries
and the complete Launcher, Editor, Files, Terminal, Store, Settings, Capture,
Media Player and Notifications binaries.
Notifications keeps its original git toolkit/panel graph, config/util crates
and optional systemd feature. `native_libraries` explicitly exports those two
shared presentation crates by component-relative path and exact Cargo identity;
OS consumers link them from the same immutable native source composition.
MCP submits bounded intent through the SDK's fixed-binary cancellable stdin
transport and the OS `system.notification.control` route. The OS derives
owner/source/session authority, durably publishes before delivery, and retains
SQLite, DND/preferences, retention, credentials, audit and retry/lease ownership.
Its existing Agent bridge is the only desktop queue consumer. The native
daemon preserves freedesktop interoperability with sender-bound numeric
handles; external labels/hints cannot mutate other core records. Durable
string IDs replace MCP desktop integers explicitly, without an alias store.
Popup expiry/transient flags affect presentation, never durable acknowledgement
or retention. The Python `notify` facade now belongs to the same product and
uses the shared Python SDK's explicit installed-binary/cancellable stdin
transport. Exact native post/close and notify send/list actions remain bound
to their separate identities. Notify list uses `data.inbox.read` independently
of send's `ui.notify`, projects only that owner's `app:notify` records, and
returns a stable publication order plus full source total. Urgent is warning
severity, still subject to DND. New records live only in the OS service;
historical JSON stays untouched in its prior namespace and is excluded from
new lists, never imported/replayed or used as a failure fallback. Native
settings, identities and grants are not merged by relocation.
Headless acceptance does not establish interactive visual/full-image readiness.
Capture preserves the independent ashpd/zbus/Tokio graph, original interactive
portal experience, notifications, 72 locales and all icons/build inputs. It has
no libcosmic renderer or file-chooser dependency to replace. Non-interactive
UI/CLI and MCP use the same typed OS service and fixed product-native PNG pipe
mode. The broker requires `desktop.capture:screen` separately from exact
destination write authority, bounds the owner-session process and persists
non-overwriting private output with OS task snapshots. MCP holds no session
bus, exposes no interactive/clipboard or arbitrary native launch route, and
does not call another App. Existing screenshot/configuration paths do not move.
The new screen grant requires explicit consent; identities are not renamed.
Direct human CLI requests retain an already-connected stderr terminal for the
existing OS session bootstrap; unauthenticated headless requests remain denied.

Settings preserves its nested workspace, all default pages, original toolkit
patches and config-schema dependencies. Applications now presents verified App
permissions through the same OS client as four permission-management MCP tools.
Those tools require only `sys.permissions:manage`, never target provider grants.
Requests are pending until the OS polkit helper confirms; revocation and live
enforcement remain in the OS. Until-revoked restoration is durable policy
consent rather than expiring execution authority; old approved Settings receipts
retain that meaning while newer owner/App/session revocations still win.
The shared permission client explicitly selects installed `/usr/local/bin/cos`
through the SDK decoder without relying on PATH or changing process environment.
Fixed Settings activation uses the authenticated owner's independent user
systemd service, preserving daemon/worker `NoNewPrivileges` and immediate
startup error reporting without tying the GUI lifetime to the broker.
Only the human UI may present polkit confirmation; no approval route is
available to MCP. Fixed brokered permissions can be disabled and
restored; direct resources and argument-bound scopes are explicitly unsupported.
The original discovery and fixed-target activation tools remain unchanged.
Human UI adapters use OS filesystem/process services and SDK policy/snapshots,
reject MCP entry, and never dispatch Files or Terminal Apps. Existing direct
D-Bus/Wayland behavior remains human-only; credentials/configuration and backend
consolidation are not part of source relocation. Store
preserves its standalone default-feature graph and nested flathub-stats helper.
Its native queries embed the canonical product catalog library, never the pkg
App entrypoint or transaction identity. Native UI ref reads/data cleanup use
OS policy and snapshots; fixed Store activation uses its existing proc.spawn
grant. Interactive Flatpak/PackageKit backends and human policies are unchanged;
their catalogs/data are not consolidated with MCP by this source relocation.
Terminal retains
its original upstream toolkit/file-chooser and renderer graph. Native MCP
embeds the canonical Terminal command library for bounded run/PATH lookup;
native launch and UI snapshots go through controlled OS services, not Apps.
`cosmic-term` and `exec` retain independent grants and process state, and caller
metadata never substitutes the worker's authenticated broker session.
Files retains its
original locked toolkit patches and workspace, including the applet executable.
Its private native bridge embeds the canonical product filesystem/Recoll and
document parsing sources, calling only system-installed SDK/runtime authority.
The pure document parsing/conversion library also ships in the Agent package
for the remaining Document App; native builds embed the same source rather
than loading mutable App scripts. Summary memory belongs to `cosmic-files`,
metadata's tag sidecar needs an exact parent read, and reveal is the fixed OS
Files target. Existing UI hot-path/cache/backend consolidation is separate.
Editor retains its original
locked upstream toolkit/file-chooser graph and immutable SDK/runtime. Its
interactive unsaved-buffer AI actions share the MCP SDK helper rather than
calling the Document App; both retain the Editor identity and untrusted-content
origin. Neither AI path saves files or memory. Launcher additionally uses immutable
OS SDK/runtime and launcher-backend library/service sources. Its native MCP
embeds the canonical Python product implementation and SDK adapter at compile
time, then replaces its process with isolated system Python; no mutable App
script or App intercall is involved. The OS-supplied SDK authenticates native
calls and the runtime checks exact scopes before the typed launch service.
The native UI service's catalog/history and per-App MCP data remain separate.

Desktop Widgets uses typed `Providers` callbacks for Calendar, read-only Agent
tasks and telemetry. OS shared services retain exact policy checks, data paths,
bounded commands and existing Linux telemetry fallback. Agent Activity shares
only the OS read-only task adapter; no App calls another App. Sampling state
stays process-local in the host, while the complete original rail UI, refresh
guards, suggestions, resources and tests are product-owned. The descriptor and
linked shell remain desktop-package assets. This move does not introduce a new
Agent executor, data owner or visual redesign.

Media Player preserves the full standalone native video/audio UI, renderer
and optional dependency graph, thumbnailer and 72 locales. Its MPRIS backend
publishes the native UI's state and routes controls through the same UI event
loop, including a working Stop/reset action. MCP holds no bus and no second
playback cache. The fixed OS adapter verifies owner, installed native process
and unique MPRIS connection, with independent exact observation/control
consent and a fresh dispatch gate. Missing, spoofed or ambiguous instances
fail instead of selecting another player. No App calls, arbitrary launch or
open-media route are exposed. Installed identity, data and configuration
remain unchanged; private-bus fixtures are not interactive playback acceptance.
