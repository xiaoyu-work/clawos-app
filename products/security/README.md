# Security

`security-center` exposes seven MCP tools for security summary, authentication,
SSH, sudo, mandatory access control, listening ports and security events.
All retain the existing sensitive `sys.security:audit` permission.

The OS still collects and analyzes security evidence. This source move does
not modify security configuration, copy journals or introduce a new GUI.
`firewall-manager` also lives here, with status/add/delete/clear/restore MCP
tools. Its observation and control permissions stay separate; nftables
execution, durable state and owner-bound rollback remain in the OS. Clear and
restore still require explicit confirmation. USB management awaits migration;
its control permissions must not be combined with inspection or firewall authority.

See [MODULE.md](MODULE.md) for source navigation and commands.
