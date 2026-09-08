# Security

`security-center` exposes seven MCP tools for security summary, authentication,
SSH, sudo, mandatory access control, listening ports and security events.
All retain the existing sensitive `sys.security:audit` permission.

The OS still collects and analyzes security evidence. This source move does
not modify security configuration, copy journals or introduce a new GUI.
`firewall-manager` also lives here, with status/add/delete/clear/restore MCP
tools. Its observation and control permissions stay separate; nftables
execution, durable state and owner-bound rollback remain in the OS. Clear and
restore still require explicit confirmation.

`usb-guard` provides status/authorize/block/unblock/eject/restore. Enabling a
device needs no confirmation; disabling it and other control actions require
confirmation. Device revalidation, protected-storage checks, udev rules, safe
eject and rollback remain OS-owned.

All three assigned App sources have moved. This does not create a unified GUI,
merge state or combine inspection, firewall and USB permissions.

See [MODULE.md](MODULE.md) for source navigation and commands.
