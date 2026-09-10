# Clipboard Product

Own `clipboard-manager`'s status/types/read/write/clear MCP tools and the complete
native `panel-clipboard` presentation and CopyQ history implementation.

| Path | Responsibility |
| --- | --- |
| `apps/clipboard-manager/app.json` | Selection read/write grants, exact source read and clear confirmation |
| `apps/clipboard-manager/main.py` | Selection/MIME/source validation and typed `cos __clipboard` requests |
| `apps/clipboard-manager/server.py` | Direct SDK MCP handlers |
| `apps/clipboard-manager/test_main.py` | Direct/SDK routes, selection defaults, scopes, validation and broker errors |
| `apps/panel-clipboard/` | Standalone human-only native launcher, unchanged manifest and named history grants |
| `native/claw-applet-clipboard/` | Native popup, history refresh/restore/delete/clear, CopyQ scripts, translations, desktop entry and synthetic Rust tests |
| `native/claw-applet-clipboard/src/main.rs`, `src/service.rs` | Standalone binary entry and public OS SDK history-permission client |
| `native/claw-applet-clipboard/build.rs`, `justfile` | Product-owned desktop localization and native installation |
| `native/Cargo.lock`, `../../tools/native_build.py` | Locked native binary/test build against declared SDK/toolkit inputs |
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
The standalone `/usr/bin/claw-applet-clipboard` retains its `HistoryPolicy`
callback seam. Its production callback uses the public SDK's fixed OS applet
provider, mapping read/write requests only to `Name(history)`.
The product checks authorization before each CopyQ action, including both read
and write before restore/delete; clear requires write. It does not depend on
Widget Rail or another App. The icon stays the toolkit's `edit-paste-symbolic`.
Native runtime separation does not unify CopyQ history with Wayland selection.
Explicit backend integration remains separate work; do not merge scopes.
Apps never invoke other Apps.

The Rust UI retains the normal verified App manifest, identity/session,
capability and sandbox contract. Its language, publisher and delivery format
confer no privilege or native App allowlist entry. The public data interface
uses the same resource checks for every App. A history permission preflight
does not itself execute or authorize an unchecked backend operation.

```bash
python3 tools/test.py clipboard
python3 tools/stage.py clipboard --root build/clipboard-stage
python3 tools/native_build.py clipboard test
```

Tests use synthetic history and broker responses, never live clipboard content
or CopyQ commands. Native tests cover policy denial, stale generations, closed
popup results and clear/busy guards as well as the original parser/scripts.
The product's `just install` installs the real compiled standalone binary and
generated `com.clawos.AppletClipboard.desktop`, with the original shared icon.
This is build-time file staging with an explicit non-root `rootdir`, not an
installed-system hook or permission installer.
The independent App package requires `claw-os-applet-services-v1 (= 1)`; the
OS shell no longer links this UI or generates its resources. The native
integration test executes the actual ELF without desktop transports. These
headless checks do not establish interactive Wayland acceptance.
