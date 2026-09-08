# Settings Product

Own `accessibility-manager`'s five MCP tools, `audio-manager`'s ten audio tools,
and `bluetooth-manager`'s twelve device-lifecycle tools. Native `cosmic-settings`
and other system-management Apps await their individual migrations.

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

Settings organizes interfaces, not a union of authority. Each provider must
retain its own App identity, scope checks and consent boundary. Apps do not
call one another; moving a native launcher alone is not a complete UI migration.

```bash
python3 tools/test.py settings
python3 tools/stage.py settings --root build/settings-stage
```

Tests use synthetic broker responses and do not change desktop, audio or Bluetooth state.
