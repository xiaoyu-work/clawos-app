# Clipboard Product

Own `clipboard-manager`'s status/types/read/write/clear MCP tools. Native
`panel-clipboard` presentation and its CopyQ history integration remain pending.

| Path | Responsibility |
| --- | --- |
| `apps/clipboard-manager/app.json` | Selection read/write grants, exact source read and clear confirmation |
| `apps/clipboard-manager/main.py` | Selection/MIME/source validation and typed `cos __clipboard` requests |
| `apps/clipboard-manager/server.py` | Direct SDK MCP handlers |
| `apps/clipboard-manager/test_main.py` | Direct/SDK routes, selection defaults, scopes, validation and broker errors |
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
Native UI/build migration and explicit backend integration are separate work;
do not merge scopes or move only its launcher and claim the panel is complete.
Apps never invoke other Apps.

```bash
python3 tools/test.py clipboard
python3 tools/stage.py clipboard --root build/clipboard-stage
```

Tests use temporary source files and synthetic broker responses, never live clipboard content.
