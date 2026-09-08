# Backup and Recovery

`backup-center` manages mounted local Restic repositories through seven MCP
tools: initialize, list snapshots, check, back up, restore, forget and retain.
Restore, forgetting a snapshot and retention pruning require explicit
confirmation. Repository/data paths and credential references retain their
exact capability scopes.

`system-snapshot` exposes five tools to inspect support, list, create and
delete recovery points, or schedule a confirmed rollback. The OS owns the
Snapper/Btrfs/LVM backends and snapshot index.

These source moves preserve both installed identities, existing data and
permissions. Execution and credentials stay behind the Claw OS broker.
Data backup and whole-system recovery do not share permissions merely because
they belong to one product; neither App calls the other.

See [MODULE.md](MODULE.md) for source navigation and commands.
