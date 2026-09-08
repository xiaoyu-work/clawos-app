# Backup and Recovery

`backup-center` manages mounted local Restic repositories through seven MCP
tools: initialize, list snapshots, check, back up, restore, forget and retain.
Restore, forgetting a snapshot and retention pruning require explicit
confirmation. Repository/data paths and credential references retain their
exact capability scopes.

This source move preserves installed identity and existing backup data.
Restic execution and credentials stay behind the Claw OS broker. The
`system-snapshot` App remains in Claw OS pending its own migration; data backup
and whole-system recovery do not share permissions merely because they belong
to one product.

See [MODULE.md](MODULE.md) for source navigation and commands.
