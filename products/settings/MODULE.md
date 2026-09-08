# Settings Product

Own `accessibility-manager`'s five MCP tools, `audio-manager`'s ten audio tools,
`bluetooth-manager`'s twelve device-lifecycle tools, `camera-manager`'s
two discovery/capture tools, `display-manager`'s ten output/backlight tools,
`desktop-manager`'s four window-management tools and `location-manager`'s
two location/timezone tools, plus `network-manager`'s eleven network tools,
`power-manager`'s seven status/power tools and `printer-manager`'s five
discovery/queue/printing tools, and `user-manager`'s twelve identity tools.
All eleven management App sources assigned to Settings have moved.
The complete native `cosmic-settings` workspace, UI, MCP and resources also live
here, retaining its separate twelfth identity and original default pages.

| Path | Responsibility |
| --- | --- |
| `apps/accessibility-manager/app.json` | Separate observation/control scopes and closed toggle/filter choices |
| `apps/accessibility-manager/main.py` | Validated `cos __accessibility` requests |
| `apps/accessibility-manager/server.py` | Direct SDK MCP handlers |
| `apps/accessibility-manager/test_main.py` | All SDK routes/choices, exact scopes and pre-policy validation |
| `apps/audio-manager/app.json` | Separate audio observation, output, microphone and media-route scopes |
| `apps/audio-manager/main.py`, `server.py` | Validated `cos __audio` requests and direct SDK MCP handlers |
| `apps/audio-manager/test_main.py` | Direct/SDK routes, exact scopes/argv, numeric bounds and broker errors |
| `apps/bluetooth-manager/app.json` | Observation/control scopes, scan default and pairing contracts |
| `apps/bluetooth-manager/main.py`, `server.py` | Validated `cos __bluetooth` requests and SDK handlers; pairing responses use stdin |
| `apps/bluetooth-manager/test_main.py` | Direct/SDK routes, MAC/ID normalization, validation and stdin-only pairing responses |
| `apps/camera-manager/app.json` | Separate observation, camera capture and exact destination write scopes |
| `apps/camera-manager/main.py`, `server.py` | Validated `cos __camera` requests and SDK handlers with bounded capture dimensions |
| `apps/camera-manager/test_main.py` | Direct/SDK PNG/JPEG routes, default/explicit dimensions and pre-policy validation |
| `apps/display-manager/app.json` | Observation/manage scopes, exact layout-read scope and explicit confirmation |
| `apps/display-manager/main.py`, `server.py` | Validated `cos __display` requests and direct SDK handlers |
| `apps/display-manager/test_main.py` | Direct/SDK routes, optional mode fields, numeric bounds and strict confirmation |
| `apps/desktop-manager/app.json` | Separate desktop observation, window control and exact AppID launch grants |
| `apps/desktop-manager/main.py`, `server.py` | Validated `cos __desktop` window requests and direct SDK handlers |
| `apps/desktop-manager/test_main.py` | All direct/SDK routes, exact scopes/argv, identifier validation and broker failures |
| `apps/location-manager/app.json` | Existing location grant, five accuracy choices and city default |
| `apps/location-manager/main.py`, `server.py` | Validated `cos __location` requests and direct SDK handlers |
| `apps/location-manager/test_main.py` | Both direct/SDK routes across every accuracy/default and pre-policy validation |
| `apps/network-manager/app.json` | Separate observation/Wi-Fi/VPN/airplane scopes and conditional exact secret grant |
| `apps/network-manager/main.py`, `server.py` | Validated `cos __network` requests and SDK handlers using credential references |
| `apps/network-manager/test_main.py` | All direct/SDK routes, open/protected Wi-Fi, radio states and exact scopes/argv |
| `apps/power-manager/app.json` | Separate power observation and critical system power grant; explicit true confirmation |
| `apps/power-manager/main.py`, `server.py` | Validated `cos __power` requests and direct SDK handlers |
| `apps/power-manager/test_main.py` | All direct/SDK routes, strict confirmation for all six mutations and broker errors |
| `apps/printer-manager/app.json` | Separate discovery/queue/print/control grants and exact source-file read scope |
| `apps/printer-manager/main.py`, `server.py` | Validated `cos __printer` requests and SDK handlers with bounded print options |
| `apps/printer-manager/test_main.py` | Direct/SDK routes, optional printer, all duplex choices, print defaults and strict cancel confirmation |
| `apps/user-manager/app.json` | Separate identity observation/manage grants and exact password credential read |
| `apps/user-manager/main.py`, `server.py` | Validated `cos __users` requests and SDK handlers; no password plaintext |
| `apps/user-manager/test_main.py` | All direct/SDK routes, optional creation fields, group/token normalization and destructive confirmation |
| `package.json` | Product-owned staging and test inputs |
| `native/cosmic-settings/` | Entire independent GPL workspace, lock, all page/subscription crates and resource/config/translation inputs |
| `native/cosmic-settings/cosmic-settings/src/mcp.rs` | Static page catalog/search and fixed OS Settings activation |
| `native/cosmic-settings/cosmic-settings/src/claw_glue.rs`, `src/human.rs`, `human_bridge.py` | Human-only controlled filesystem/process/policy/snapshot adapters and SDK Agent context; no App dispatch |
| `native/test_build.py`, `native/test_process.py` | Workspace/default graph, synthetic human adapters, installed resources and authenticated stdio MCP |

Preserve the installed App identity. Status requires `sys.observe` scope
`accessibility`; mutations require `ui.accessibility` scope `control`.
The OS owns user-session validation, Wayland helper execution, AT-SPI state
changes and serialization. Existing accessibility state does not move.

`audio-manager` keeps its separate installed identity. Status uses
`sys.observe:audio`, output controls use `device.audio:output`, input controls
use `device.microphone:input`, and defaults/routes/profiles use
`device.media-route:pipewire`. The OS owns user-session validation, PipeWire
and WirePlumber execution, and mutation serialization. Source relocation does
not change live volume, mute, routing or profile state.

`bluetooth-manager` retains `sys.observe:bluetooth` for status and
`device.bluetooth:control` for device operations. BlueZ execution, saved device
state, owner-bound pairing sessions and their lifetime remain OS-owned.
Pairing responses stay off broker argv and go through stdin. Relocation does
not pair, forget, trust or change any live device.

`camera-manager` retains `sys.observe:camera` for status. Capture requires both
`device.camera:capture` and `fs.write` on the exact canonical new destination.
The OS owns user-session/PipeWire access, node-serial revalidation, GStreamer
execution and bounded, non-overwriting image persistence. Relocation does not
move captured images or activate cameras.

`display-manager` retains `sys.observe:display` and `device.display:manage`.
Applying a layout also requires `fs.read` on its exact canonical source path.
Apply/restore require explicit confirmation. COSMIC output control, kernel
backlights, mutation serialization and owner-bound backup/restore state remain
OS-owned; source relocation does not change the current display layout.

`desktop-manager` retains `sys.observe:desktop` for listing and
`desktop.window:control` for focus/close/restart. Restart also requires
`desktop.launch` for the exact compositor AppID. The OS owns Wayland access,
window identity checks, close completion and native relaunch. This uses a typed
OS service, not another App's business/MCP interface; the App cannot invoke the
separate `launcher`-owned generic launch route.

`location-manager` keeps the existing `device.location` Wild-scope grant for
both queries, its five accuracy choices and the `city` default. GeoClue access
runs under the requesting desktop user through the OS helper; offline timezone
suggestions stay OS-owned and do not change the system timezone. Relocation
does not add permissions, perform location requests or move location data.

`network-manager` preserves `sys.observe:network` and separate `net.manage`
scopes for `wifi`, `vpn` and `airplane`. Wi-Fi credentials are optional references
requiring exact `secret.read`; only the OS loads the password. NetworkManager
execution, profile/device validation, mutation serialization and before/after
state collection remain OS-owned. No saved profiles, passwords or live network
state move, and the App does not execute `nmcli` directly.

`power-manager` retains `sys.observe:power` for status and the existing
`sys.power` Wild-scope grant for six machine-wide actions. Each action requires
the exact boolean `confirm=true` before policy. UPower/logind access, capability
checks, mutation serialization and power execution remain OS-owned. Neither
source relocation nor product tests issue real sleep, reboot or shutdown calls.

`printer-manager` retains `sys.observe:printing` for discovery/capabilities
and separate `device.printer` scopes for queue observation, printing and
control. Printing also requires `fs.read` on the exact canonical source;
cancellation requires explicit confirmation. CUPS execution, pinned source-file
descriptors, job-owner checks and mutation serialization remain OS-owned.
Existing queues/documents stay in place; tests do not submit or cancel real jobs.

`user-manager` retains `sys.observe:identities` for status and
`sys.identity:manage` for mutations. Password changes also require exact
`secret.read` authority on a credential reference. Local account/group state,
password handling, shadow utilities, shell allowlisting and owner-bound rollback
remain OS-owned. Deletion retains home directories; destructive actions keep
explicit confirmation. Tests do not change real users, groups or passwords.

Settings organizes interfaces, not a union of authority. Each provider must
retain its own App identity, scope checks and consent boundary. Apps do not
call one another. Native MCP has only `settings.list_pages`, `settings.search`
and `settings.open`. The first two require no device authority; opening uses
only `proc.spawn:cosmic-settings` at the fixed OS Settings target. Optional page
ids are checked against the native CLI's page commands before crossing the
service boundary, including its existing magnifier and dock/panel-applet pages.

The native human UI retains its original D-Bus/Wayland and configuration
behavior, not the eleven Apps' combined grants. Former filesystem/exec App
bridges now use controlled OS text writes, registered process spawning and
human-only SDK policy/snapshot adapters. Queries remain timeout/output bounded
and credential-scrubbed. These adapters reject MCP before any policy or effect.
Provider credentials, consent, settings-daemon/config services and user state
stay OS-owned. Source completion is not backend/data consolidation or visual
and hardware acceptance.

```bash
python3 tools/test.py settings
python3 tools/stage.py settings --root build/settings-stage
python3 tools/native_build.py settings test
python3 tools/native_build.py settings build
python3 products/settings/native/test_process.py
```

Tests use synthetic broker responses and do not change device state or capture images.
Native builds require the normal toolkit libraries plus PipeWire, PulseAudio,
xkbregistry, libclang and gettext development inputs. Native process tests use
`just` and Bubblewrap for scratch installation and an isolated synthetic broker.
