# Settings

`accessibility-manager` exposes five MCP tools for accessibility status,
screen reader, magnifier, inversion and color-vision filters. The existing
toggle/filter choices and separate observation/control scopes are preserved.

Wayland and AT-SPI execution, user-session validation and state remain behind
the Claw OS broker. The native `cosmic-settings` UI and other system-management
Apps are still pending; this product must not become a super-privileged
Settings process or call other Apps to obtain their authority.

See [MODULE.md](MODULE.md) for source navigation and commands.
