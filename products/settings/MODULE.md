# Settings Product

Own `accessibility-manager`'s five MCP tools, `audio-manager`'s ten audio tools,
`bluetooth-manager`'s twelve device-lifecycle tools, `camera-manager`'s
two discovery/capture tools, `display-manager`'s ten output/backlight tools
`desktop-manager`'s four window-management tools and `location-manager`'s
two location/timezone tools.
Native `cosmic-settings` and other system-management Apps await their
individual migrations.

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
| `package.json` | Product-owned staging and test inputs |

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

Settings organizes interfaces, not a union of authority. Each provider must
retain its own App identity, scope checks and consent boundary. Apps do not
call one another; moving a native launcher alone is not a complete UI migration.

```bash
python3 tools/test.py settings
python3 tools/stage.py settings --root build/settings-stage
```

Tests use synthetic broker responses and do not change device state or capture images.
