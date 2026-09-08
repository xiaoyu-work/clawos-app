# Maintenance

`config-editor` exposes inspect, validate, apply and restore MCP tools for
supported system configuration files. It retains exact target/source
permissions, canonical path validation and explicit mutation confirmation.

The OS provides validators, atomic replacement and durable rollback. Moving
App source does not move or reset `/etc` files or backup state.
The `systemd` App awaits migration; this product does not introduce a unified
GUI, a generic shell interface or App-to-App calls.

See [MODULE.md](MODULE.md) for source responsibilities and commands.
