# Backup and Recovery Product

Own the `backup-center` App's seven MCP tools for mounted local Restic
repositories. Whole-system recovery is a distinct contract: `system-snapshot`
has not migrated yet and must not inherit data-backup permissions.

| Path | Responsibility |
| --- | --- |
| `apps/backup-center/app.json` | Repository/source/destination scopes, credential reference and explicit confirmation |
| `apps/backup-center/main.py` | Validated backup lifecycle requests through `cos __backup` |
| `apps/backup-center/server.py` | Direct SDK MCP handlers |
| `apps/backup-center/test_main.py` | Argument validation, exact capabilities/argv, SDK dispatch and broker errors |
| `package.json` | Product-owned staging and test inputs |

Preserve the installed `backup-center` identity: the OS provider binds
authority to it. Repository and restored-data paths remain user-selected,
canonical paths; relocation does not move or delete existing backups.
The App passes a credential reference, not a password, to the OS broker.
Restic execution, credential loading, mount checks, owner identity and
privileged authorization remain OS-owned. Apps do not call one another.

```bash
python3 tools/test.py backup-recovery
python3 tools/stage.py backup-recovery --root build/backup-recovery-stage
```

Tests use synthetic broker responses and do not modify live backup data.
