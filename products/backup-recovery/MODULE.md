# Backup and Recovery Product

Own the `backup-center` App's seven MCP tools for mounted local Restic
repositories and `system-snapshot`'s five tools for whole-system recovery.
These remain distinct contracts and must not inherit one another's permissions.

| Path | Responsibility |
| --- | --- |
| `apps/backup-center/app.json` | Repository/source/destination scopes, credential reference and explicit confirmation |
| `apps/backup-center/main.py` | Validated backup lifecycle requests through `cos __backup` |
| `apps/backup-center/server.py` | Direct SDK MCP handlers |
| `apps/backup-center/test_main.py` | Argument validation, exact capabilities/argv, SDK dispatch and broker errors |
| `apps/system-snapshot/app.json` | Named observation, machine-wide snapshot authority and rollback confirmation |
| `apps/system-snapshot/main.py`, `server.py` | Direct SDK handlers and validated `cos __snapshot` broker requests |
| `apps/system-snapshot/test_main.py` | MCP contract/dispatch, snapshot IDs, defaults, confirmation and broker failures |
| `package.json` | Product-owned staging and test inputs |

Preserve the installed `backup-center` identity: the OS provider binds
authority to it. Repository and restored-data paths remain user-selected,
canonical paths; relocation does not move or delete existing backups.
The App passes a credential reference, not a password, to the OS broker.
Restic execution, credential loading, mount checks, owner identity and
privileged authorization remain OS-owned. Apps do not call one another.

Preserve the `system-snapshot` identity and existing snapshot IDs. Its index,
Snapper/Btrfs/LVM execution, rollback scheduling and reconciliation stay in
the OS provider. Source relocation does not create/delete snapshots or move
their data. The named `sys.observe` scope and existing `sys.snapshot` authority
are unchanged; rollback still requires explicit confirmation.

```bash
python3 tools/test.py backup-recovery
python3 tools/stage.py backup-recovery --root build/backup-recovery-stage
```

Tests use synthetic broker responses and do not modify live backups or snapshots.
