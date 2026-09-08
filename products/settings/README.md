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

Wayland, AT-SPI and PipeWire/WirePlumber execution and user-session validation remain behind
the Claw OS broker. The native `cosmic-settings` UI and other system-management
Apps are still pending; this product must not become a super-privileged
Settings process or call other Apps to obtain their authority.

See [MODULE.md](MODULE.md) for source navigation and commands.
