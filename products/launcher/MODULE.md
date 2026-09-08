# Launcher Product

Own the Python `launcher` App's five MCP tools. Native `cosmic-launcher` UI,
build/resources and replacement of its legacy App forwarding remain pending.

| Path | Responsibility |
| --- | --- |
| `apps/launcher/app.json` | Catalog read grants, exact AppID/file launch grants and process observation |
| `apps/launcher/main.py` | XDG desktop catalog, localized search, typed launch requests and recent-file handling |
| `apps/launcher/server.py` | Direct SDK list/find/open/recent/is-running handlers |
| `apps/launcher/test_main.py` | Desktop parsing, scopes, URI/path safety, broker errors, recent state and SDK dispatch |
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

Do not count a native launcher manifest-only move as completed UI migration.
Its current `cos app launcher` forwarding must be replaced with shared
product logic and controlled OS services, not retained as App-to-App calls.

```bash
python3 tools/test.py launcher
python3 tools/stage.py launcher --root build/launcher-stage
```

Tests use temporary desktop entries/history and synthetic process/broker replies;
no GUI program is launched.
