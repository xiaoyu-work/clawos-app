# Events and Audit

`event-center` exposes event-source health, bounded recent-event queries and
process-exit subscriptions through three MCP tools. All retain the existing
sensitive `sys.events:observe` grant.

The OS owns subscriptions, event records and pidfd watches. This source move
does not create a new journal or merge events into audit or notifications.
The `log` App awaits migration; a unified presentation is not implemented here.

See [MODULE.md](MODULE.md) for source responsibilities and commands.
