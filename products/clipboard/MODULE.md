# Clipboard Product

Own `clipboard-manager`'s status/types/read/write/clear MCP tools and the complete
native `panel-clipboard` presentation and CopyQ history implementation.

| Path | Responsibility |
| --- | --- |
| `apps/clipboard-manager/app.json` | Selection read/write grants, exact source read and clear confirmation |
| `apps/clipboard-manager/main.py` | Selection/MIME/source validation and typed `cos __clipboard` requests |
| `apps/clipboard-manager/server.py` | Direct SDK MCP handlers |
| `apps/clipboard-manager/test_main.py` | Direct/SDK routes, selection defaults, scopes, validation and broker errors |
| `apps/panel-clipboard/` | Unchanged human-only shell launcher, manifest and named history grants |
| `native/claw-applet-clipboard/` | Native popup, history refresh/restore/delete/clear, CopyQ scripts, translations, desktop entry and synthetic Rust tests |
| `native/Cargo.lock`, `../../tools/native_build.py` | Locked native development build against the shared OS toolkit |
| `PROVENANCE.md`, `native/LICENSE` | Source origin and preserved GPL terms |
| `package.json` | Product-owned staging and test inputs |

Preserve installed identity and separate `clipboard.read:selection` from
`clipboard.write:selection`. Write additionally needs `fs.read` for its exact
canonical source path. Clear requires exact true confirmation. The primary
selection is opt-in; omitted MIME stays omitted at the App boundary so the OS
can supply its existing default.

The OS owns user-session/Wayland validation, wl-clipboard execution, bounded
content transfer, source descriptors and write serialization. App code does
not read the compositor or execute wl-copy/wl-paste directly. Relocation copies
no clipboard contents, history or session state.

The panel's existing CopyQ `history` scopes are not the same as `selection`.
The OS shell links the product library and supplies its `HistoryPolicy` callback,
mapping read/write requests to `Name(history)` through the shared policy service.
The product checks authorization before each CopyQ action, including both read
and write before restore/delete; clear requires write. It does not depend on
Widget Rail or another App. The icon stays the toolkit's `edit-paste-symbolic`.
Native source/build migration does not unify CopyQ history with Wayland selection.
Explicit backend integration remains separate work; do not merge scopes.
Apps never invoke other Apps.

```bash
python3 tools/test.py clipboard
python3 tools/stage.py clipboard --root build/clipboard-stage
python3 tools/native_build.py clipboard test
```

Tests use synthetic history and broker responses, never live clipboard content
or CopyQ commands. Native tests cover policy denial, stale generations, closed
popup results and clear/busy guards as well as the original parser/scripts.
The OS desktop package still owns the wrapper and linked binary; the selection
App remains in the Agent package, with signed APT update behavior unchanged.
