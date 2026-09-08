# Files Product

Own the Files MCP operations, argument contract, file metadata behavior and
product tests. The OS owns filesystem authority, sandbox mounts and snapshots.

| Path | Responsibility |
| --- | --- |
| `apps/fs/app.json` | Fourteen MCP tools with exact filesystem scopes |
| `apps/fs/main.py` | Bounded text/binary IO, metadata, search and file operations |
| `apps/fs/server.py` | Direct SDK MCP handlers with authenticated snapshot sessions |
| `apps/fs/test_main.py` | Filesystem, framing, validation and authority regressions |
| `package.json` | Product-owned App staging and test inputs |

The source move preserves `fs`, its manifest, runtime behavior and installed
path. Shared helpers come from the immutable platform library dependency.
No App-to-App calls or duplicated OS services are introduced. The native
Files UI and document operations remain in the OS repository until their own
complete source/build migrations.
The search implementation and its tests require the system `ripgrep` package.

```bash
python3 tools/test.py files
python3 tools/stage.py files --root build/files-stage
```
