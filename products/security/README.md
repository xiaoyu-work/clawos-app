# Security

`security-center` exposes seven MCP tools for security summary, authentication,
SSH, sudo, mandatory access control, listening ports and security events.
All retain the existing sensitive `sys.security:audit` permission.

The OS still collects and analyzes security evidence. This source move does
not modify security configuration, copy journals or introduce a new GUI.
Firewall and USB management await separate migrations; their control
permissions must not be combined with inspection authority.

See [MODULE.md](MODULE.md) for source navigation and commands.
