# Maintenance Product

Own `config-editor`'s inspect/validate/apply/restore MCP tools. The assigned
`systemd` App awaits its individual migration.

| Path | Responsibility |
| --- | --- |
| `apps/config-editor/app.json` | Exact target/source grants and apply/restore confirmation |
| `apps/config-editor/main.py` | Canonical path checks, token normalization and typed `cos __config` requests |
| `apps/config-editor/server.py` | Direct SDK MCP handlers |
| `apps/config-editor/test_main.py` | Direct/SDK routes, exact scopes, invalid inputs and broker errors |
| `package.json` | Product-owned staging and test inputs |

Preserve the installed `config-editor` identity. Every tool requires
`sys.config` for its exact canonical target below `/etc`; validate/apply also
require `fs.read` for the exact staged source. Inspect does not substitute
ordinary observation authority for sensitive configuration access.
Apply/restore require exact boolean confirmation. Replacement content stays
in the source file, not command-line arguments.

The OS owns the supported-target validator registry, bounded file reads,
nofollow/identity checks, mutation serialization, metadata-preserving atomic
replacement and durable owner-bound backups. This repository does not own
system configuration or backup state. Product grouping does not grant general
shell access or combine configuration and service-management authority.
Apps never call other Apps.

```bash
python3 tools/test.py maintenance
python3 tools/stage.py maintenance --root build/maintenance-stage
```

Tests use synthetic filesystem/broker boundaries; no live configuration is changed.
