# Events and Audit

`event-center` exposes event-source health, bounded recent-event queries and
process-exit subscriptions through three MCP tools. All retain the existing
sensitive `sys.events:observe` grant.

The OS owns subscriptions, event records and pidfd watches. This source move
does not create a new journal or merge events into audit or notifications.
`log` also lives here, retaining read/tail/search/manual-write operations and
their existing grants. It is a legacy direct JSONL implementation, not an OS
audit-service client: the isolated App data directory is not the authoritative
system audit trail. No runtime logs are copied or audit access expanded.

Both App sources have moved, but typed audit-service integration and unified
presentation remain pending. Do not treat manual App entries as trusted OS
audit records.

See [MODULE.md](MODULE.md) for source responsibilities and commands.
