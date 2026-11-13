# Clipboard Product

Own `clipboard-manager`'s status/types/read/write/clear MCP tools and the complete
native `panel-clipboard` presentation, MCP service and Web history workflow.

| Path | Responsibility |
| --- | --- |
| `apps/clipboard-manager/app.json` | Selection read/write grants, exact source read and clear confirmation |
| `apps/clipboard-manager/main.py` | Selection/MIME/source validation and typed `cos __clipboard` requests |
| `apps/clipboard-manager/server.py` | Direct SDK MCP handlers |
| `apps/clipboard-manager/test_main.py` | Direct/SDK routes, selection defaults, scopes, validation and broker errors |
| `apps/panel-clipboard/` | Existing identity's package-local binary manifest and exact per-tool history grants |
| `native/claw-applet-clipboard/` | Native popup, history refresh/restore/delete/clear, translations, desktop entry and synthetic Rust tests |
| `native/claw-applet-clipboard/src/main.rs`, `src/mcp.rs`, `src/service.rs` | MCP-first binary, manifest-bound tools and pinned public SDK kernel client |
| `web/` | Independent selection UI and owning history list, item selection, bounded preview and reviewed actions |
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
The native binary retains its linked shell's optional `HistoryPolicy` callback
seam and GUI behavior. The installed GUI and MCP use the pinned public SDK and
fixed OS `cos` binary directly; they do not spend a grant again in an App-local
preflight. Every actual history operation crosses the OS-owned
`system.clipboard.control` service; there is no App-side CopyQ execution,
executable override or direct fallback.
The broker revalidates the authenticated owner/session and spends the exact
rights at the actual provider dispatch, even if a linked client omits preflight.
Finite grants are spent once, not once for preflight and again for execution.

`history.list` requires only history read and returns at most 20 text previews,
each 180 Unicode characters plus an ellipsis, stable packed-item SHA-256
identities and optional copy times. `history.remove` preserves separate history
read/write; confirmed `history.clear` needs only history write.
`history.restore` preserves those history read/write rights and separately
requires `clipboard.write:selection` because CopyQ selects into the live
clipboard. The read-only history tool never requests selection authority.
The compound interactive `open` operation declares selection-write explicitly
for its Restore control; ordinary OS review/consent must authorize this added
need. Old history grants alone cannot restore, and are not widened or migrated.
Existing history remains untouched. No other App's identity, state or consent
is borrowed.

The coordinated 0.2.1 native `desktop.needs` separately requests `ui.panel`
alongside the exact history/selection rights. Protected owner approval is
required for that high-risk display capability; clipboard rights or panel
metadata do not grant it. No MCP history tool requests `ui.panel`.
The standalone entry explicitly creates the original icon-sized Layer Shell
button without keyboard interactivity and suppresses the default XDG window.
The existing history popup, optional linked policy seam and separate Root
history/selection checks remain unchanged; geometry supplies no authority.

The OS alone validates the default owner CopyQ endpoint and system executable,
holds the authenticated provider connection and executes closed scripts.
The unprivileged fixed CLI sees only a private credential-checked relay, not
the owner's raw home, Wayland transport or session bus. Operations have a
two-second deadline and bounded output; missing services are explicit errors.
The icon remains `edit-paste-symbolic`. Apps never invoke other Apps.

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
popup results, clear/busy guards, bounded broker results, MCP discovery and
explicit confirmation. OS tests own the scripts/parser and isolated typed-client,
capability-authority and synthetic Unix/executable provider fixtures.
The product's `just install` installs the real compiled standalone binary and
generated `com.clawos.AppletClipboard.desktop`, with the original shared icon.
This is build-time file staging with an explicit non-root `rootdir`, not an
installed-system hook or permission installer.
The product declares the real `bin/claw-applet-clipboard` as both primary and
MCP entry and uses the existing native payload builder/signer contract. Its
original ELF, resources and GPL license are preserved; source staging does not
invent a binary. Shared release metadata requires the Agent-provided
`claw-os-clipboard-history-v1 (= 1)` interface instead of the Desktop-only applet helper.
The native integration test executes the actual ELF without desktop transports.
These fixtures are not live installed CopyQ, Wayland or GUI acceptance, and
publication gates remain unchanged.

A separate clean OS [acceptance run](https://github.com/xiaoyu-work/claw-os/actions/runs/43404862443)
used App revision `92f389d6`, the published `0.2.1` platform and the original
signed ELF. It verified ordinary popup open/close, one real protected CopyQ
history read, exact history-read authority and whole GUI/PAM retirement.
The independent provider retained its two synthetic items after GUI retirement
and then stopped explicitly. Manual inspection of the separately checked
open-popup pixels showed both public synthetic history texts. Automated
reply-decode/text assertions remain false; the late closing frame is not the
open reader result.

A subsequent clean OS [history mutation run](https://github.com/xiaoyu-work/claw-os/actions/runs/43412198729)
exercised the original popup's delete and confirmed-clear controls. Real CopyQ
history changed from two synthetic items to the correct remaining item, then
zero. Opening the confirmation did not clear history. The five actual Root
calls spent only their respective history read, read/write, read, write and
read rights; selection rights were not borrowed. The provider retained zero
items after GUI retirement and then exited explicitly.

The coordinated Agent package, not Desktop or this App, owns the original
shared Cosmic icon theme and its attribution. Root converts CopyQ's hexadecimal
SHA-256 hashes to the unchanged public base64 raw-digest identities.
These bounded offscreen read/mutation proofs do not establish live selection
Restore, display/provider binding, hardware rendering or full publication
readiness.
