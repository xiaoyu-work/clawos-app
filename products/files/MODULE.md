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
| `apps/cosmic-files/` | Seven native MCP tools and authority/staging regressions |
| `native/cosmic-files/` | Complete native UI/library and companion executable, original toolkit graph and resources |
| `native/cosmic-files/src/claw_glue/` | Shared product bridge, SDK AI and fixed OS reveal |
| `native/cosmic-files/product_bridge.py` | Private compiled-in adapter over canonical filesystem/Recoll/parser libraries |
| `python/claw_files/document.py` | Named shared descriptor-safe parsing/conversion export, also consumed by the Document Engine capability client |
| `native/test_process.py` | Authenticated real-binary fixture against synthetic OS/model/Recoll services |

The source move preserves `fs` and `docs`, their manifests, runtime behavior
and installed paths. Shared helpers come from App-owned
[`shared/python`](../../shared/MODULE.md); SDK/runtime remain immutable platform
dependencies.
No App-to-App calls or duplicated OS services are introduced. Native source
ownership is complete, but the existing UI hot paths, settings and metadata
remain separate from MCP data. GUI mutations inherit their launch session;
they cannot run from the MCP bridge. The existing `fs` MCP mutation snapshots
continue to use the authenticated per-call context, never process environment.
Filesystem search and its tests require the system `ripgrep` package.
Document search uses the fixed system `recollq` and `recollindex` executables;
its unit tests substitute explicit local executable fixtures. The OS still
owns the background index service and supplies canonical `COS_OWNER_HOME`.
[`Document Engine`](../../capabilities/document-engine/MODULE.md) declares
`claw_files` as a library dependency, not an App call. Doc-only staging includes
the export without installing Files Apps; combined staging checks identical
library content instead of copying conflicting trees. Native Files continues
embedding this same source through its existing native asset declaration.

```bash
python3 tools/test.py files
python3 tools/stage.py files --root build/files-stage
python3 tools/native_build.py files test
python3 tools/native_build.py files build
python3 products/files/native/test_process.py
```
