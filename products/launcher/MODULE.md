# Launcher Product

Own the Python `launcher` App's five MCP tools and the complete native
`cosmic-launcher` executable, UI, four-tool MCP surface and build/resources.

| Path | Responsibility |
| --- | --- |
| `apps/launcher/app.json` | Catalog read grants, exact AppID/file launch grants and process observation |
| `apps/launcher/main.py` | XDG desktop catalog, localized search, typed launch requests and recent-file handling |
| `apps/launcher/server.py` | Direct SDK list/find/open/recent/is-running handlers |
| `apps/launcher/test_main.py` | Desktop parsing, scopes, URI/path safety, broker errors, recent state and SDK dispatch |
| `apps/cosmic-launcher/` | Unchanged native identity/permissions and authenticated adapter contracts |
| `native/cosmic-launcher/` | Complete GPL UI, compiled-in MCP adapter, upstream packaging/resources and Rust tests |
| `native/PROVENANCE.md` | Source origin, license and shared OS backend ownership |
| `package.json` | Product-owned staging and test inputs |

Preserve installed identity, XDG precedence, localization and visibility.
Open accepts bounded absolute non-file URIs and canonical existing local files;
it sends only AppID/URIs to `cos __desktop launch`, never raw Exec commands.
The OS checks App identity, exact launch/file authority, desktop session and
user environment before launching. Opening a native desktop program is not
calling another App's business/MCP interface.

Catalog reads retain declared filesystem scopes; is-running retains
`proc.observe` Wild authority. Recent history retains its existing locked,
atomic `COS_DATA_DIR/launcher/recent.jsonl` layout. No runtime state is copied.
The isolated App Host data directory is not automatically shared shell history;
native catalog/history integration must be explicit. No writable OS state
mounts or additional grants are introduced.

The native MCP process embeds the canonical product implementation
(`apps/launcher/main.py`) at compile time and serves it through the Python SDK,
not an App intercall or mutable helper script. Its fixed isolated interpreter
imports packaged OS SDK/runtime and App-owned common libraries from
`/usr/lib/cos/python`; the host's identity,
authenticated transport and per-App data directory are preserved. Both MCP
surfaces reuse catalog, launch validation and recent-file logic, without
merging grants or data partitions. Native extras preserve order, accepting
bounded absolute non-file URIs and canonical existing files with exact read
authority, never unchecked Exec arguments.

The on-screen UI continues to use the OS-owned launcher backend service and
shared restyled toolkit. That service's catalog/history is not unified with
the product MCP backend; no shell history or user state is migrated.

```bash
python3 tools/test.py launcher
python3 tools/stage.py launcher --root build/launcher-stage
python3 tools/native_build.py launcher test
python3 tools/native_build.py launcher build
python3 products/launcher/native/test_process.py
```

Tests use temporary desktop entries/history and synthetic process/broker replies;
no GUI program is launched.
The last command needs Linux bubblewrap and exercises the actual executable
with installed-layout SDK imports, an authenticated fixture transport and fake
policy/launch services. It never uses live desktop entries or user history.
