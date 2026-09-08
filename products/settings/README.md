# Settings

`accessibility-manager` exposes five MCP tools for accessibility status,
screen reader, magnifier, inversion and color-vision filters. The existing
toggle/filter choices and separate observation/control scopes are preserved.

`audio-manager` exposes ten tools for status, input/output volume and mute,
default nodes, routes and device profiles. Observation, speaker, microphone
and media-route permissions stay separate, with existing input/output limits.

`bluetooth-manager` exposes twelve tools for status, power, bounded discovery,
pairing prompts and device lifecycle control. MAC/pairing-ID normalization and
stdin-only pairing responses are preserved; BlueZ and owner-bound pairing
sessions remain OS-owned.

`camera-manager` exposes two tools for discovery and bounded PNG/JPEG still
capture. Capture requires separate camera and exact destination-write grants;
the OS rechecks node identity and persists images without overwriting.

`display-manager` exposes ten tools for output layout, mode/scale, mirroring,
backlight and restore. Apply/restore require explicit confirmation; layout
files require exact read grants. COSMIC control and backup state remain
OS-owned.

`desktop-manager` exposes four tools for listing, focusing, closing and
restarting windows. Restart requires window control plus exact AppID launch
authority and uses the OS window service, not another App's MCP interface.

`location-manager` exposes location and timezone-suggestion tools with five
accuracy levels and a city-level default. The existing location grant remains
required; the OS owns GeoClue access and offline timezone suggestions, without
changing the system timezone.

`network-manager` exposes eleven tools for network observations, Wi-Fi, VPN
and airplane mode. Each control domain retains its own grant. Optional Wi-Fi
credentials remain exact secret references; the OS loads passwords and executes
NetworkManager operations without moving existing profiles.

`power-manager` exposes status and six sleep/reboot/shutdown tools. The
observation grant stays separate from critical `sys.power` authority; each
power action requires explicit `confirm=true`. UPower/logind execution remains
in the OS, and product tests never perform real power actions.

`printer-manager` exposes five tools for discovery, capabilities, queues,
printing and cancellation. Printing keeps exact source-file read authority;
cancellation keeps explicit confirmation and OS job-owner checks. CUPS and
existing print queues remain OS-owned.

`user-manager` exposes twelve local identity tools. Observation is separate
from identity management; password changes use exact secret references, not
plaintext arguments. Account state, home directories and rollback remain
OS-owned.

Wayland, AT-SPI and PipeWire/WirePlumber execution and user-session validation remain behind
the Claw OS broker. All eleven assigned management App sources have moved,
and the complete native `cosmic-settings` UI/workspace now lives in
`native/cosmic-settings`, including every page/subscription crate, original
default features, toolkit patches, translations, resources and packaging.
This product is not a super-privileged Settings process: its twelve identities
retain independent authority and do not call other Apps.

Native MCP exposes only page listing, search and opening a page. Opening uses
the fixed OS Settings target under the existing `proc.spawn:cosmic-settings`
grant, never the management Apps' device/account permissions. Human UI writes,
spawns and snapshot-backed mutations use controlled OS services, while
interactive D-Bus/Wayland behavior and existing configuration remain unchanged.

```bash
python3 tools/test.py settings
python3 tools/native_build.py settings test
python3 tools/native_build.py settings build
python3 products/settings/native/test_process.py
```

Build/test on Linux/WSL with the native dependencies listed in the CI workflow.
The last command scratch-installs the real binary/resources and tests MCP with
a synthetic broker, without touching live accounts, devices or configuration.
Interactive Wayland/visual acceptance and provider/backend consolidation remain
separate work. See [PROVENANCE.md](PROVENANCE.md) for original ownership.

See [MODULE.md](MODULE.md) for source navigation and commands.
