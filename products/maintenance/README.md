# Maintenance

`config-editor` exposes inspect, validate, apply and restore MCP tools for
supported system configuration files. It retains exact target/source
permissions, canonical path validation and explicit mutation confirmation.

The OS provides validators, atomic replacement and durable rollback. Moving
App source does not move or reset `/etc` files or backup state.
`systemd` exposes status/start/stop/restart/reload/enable/disable MCP tools with
exact-unit observation or control grants. Systemctl execution, before/after
state and supported inverse-state rollback remain OS-owned. Its existing
contract has no confirmation parameter.

Both assigned App sources have moved. This product does not introduce a
unified GUI, a generic shell interface or App-to-App calls.

See [MODULE.md](MODULE.md) for source responsibilities and commands.
