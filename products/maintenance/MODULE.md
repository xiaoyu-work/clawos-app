# Maintenance Product

Own `config-editor`'s four MCP tools and `systemd`'s seven service-management
tools. Both assigned App sources have moved, without merging their authority.

| Path | Responsibility |
| --- | --- |
| `apps/config-editor/app.json` | Exact target/source grants and apply/restore confirmation |
| `apps/config-editor/main.py` | Canonical path checks, token normalization and typed `cos __config` requests |
| `apps/config-editor/server.py` | Direct SDK MCP handlers |
| `apps/config-editor/test_main.py` | Direct/SDK routes, exact scopes, invalid inputs and broker errors |
| `apps/systemd/` | Unit validation, exact-unit manifest grants, typed broker client and direct/SDK tests |
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

Systemd status uses `sys.observe` for the exact unit; start/stop/restart/reload/
enable/disable use `sys.service` for the exact unit. No confirmation parameter
is added. The OS owns systemctl execution, serialization, before/after state
and session mutation records. Start/stop/enable/disable prepare inverse-state
records; restart/reload do not claim reversible rollback. Unit files and
service state stay in the OS, not this product.

```bash
python3 tools/test.py maintenance
python3 tools/stage.py maintenance --root build/maintenance-stage
```

Tests use synthetic filesystem/broker boundaries; no live configuration or service is changed.
