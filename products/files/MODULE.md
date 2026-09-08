# Files Product

Own the Files MCP operations, argument contract, file metadata behavior and
product tests. The OS owns filesystem authority, sandbox mounts and snapshots.

| Path | Responsibility |
| --- | --- |
| `apps/fs/app.json` | Fourteen MCP tools with exact filesystem scopes |
| `apps/fs/main.py` | Bounded text/binary IO, metadata, search and file operations |
| `apps/fs/server.py` | Direct SDK MCP handlers with authenticated snapshot sessions |
| `apps/fs/test_main.py` | Filesystem, framing, validation and authority regressions |
| `apps/docs/app.json` | Four document MCP tools with unchanged Recoll and filesystem scopes |
| `apps/docs/main.py`, `apps/docs/server.py` | Owner-scoped Recoll queries, indexing, status and configuration |
| `apps/docs/test_main.py` | Canonical owner home, subprocess, config and capability regressions |
| `package.json` | Product-owned App staging and test inputs |

The source move preserves `fs` and `docs`, their manifests, runtime behavior
and installed paths. Shared helpers come from the immutable platform library dependency.
No App-to-App calls or duplicated OS services are introduced. The native
Files UI remains in the OS repository until its complete source/build migration.
Filesystem search and its tests require the system `ripgrep` package.
Document search uses the fixed system `recollq` and `recollindex` executables;
its unit tests substitute explicit local executable fixtures. The OS still
owns the background index service and supplies canonical `COS_OWNER_HOME`.

```bash
python3 tools/test.py files
python3 tools/stage.py files --root build/files-stage
```
