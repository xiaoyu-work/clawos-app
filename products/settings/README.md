# Settings

`accessibility-manager` exposes five MCP tools for accessibility status,
screen reader, magnifier, inversion and color-vision filters. The existing
toggle/filter choices and separate observation/control scopes are preserved.

`audio-manager` exposes ten tools for status, input/output volume and mute,
default nodes, routes and device profiles. Observation, speaker, microphone
and media-route permissions stay separate, with existing input/output limits.

Wayland, AT-SPI and PipeWire/WirePlumber execution and user-session validation remain behind
the Claw OS broker. The native `cosmic-settings` UI and other system-management
Apps are still pending; this product must not become a super-privileged
Settings process or call other Apps to obtain their authority.

See [MODULE.md](MODULE.md) for source navigation and commands.
