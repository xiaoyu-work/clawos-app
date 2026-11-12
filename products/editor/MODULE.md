# Editor Product

Own the complete `cosmic-edit` native UI, MCP handlers, AI presentation,
resources, translations, build inputs and descriptor.

| Path | Responsibility |
| --- | --- |
| `apps/cosmic-edit/app.json` | Seven tools, exact file scopes, fixed desktop launch and AI budget |
| `native/cosmic-edit/src/main.rs` | Native editor UI and unsaved-buffer AI requests |
| `native/cosmic-edit/src/cli.rs`, `native/cosmic-edit/test/unit/cli.rs` | OS-native startup paths and bounded GUI argv regressions |
| `native/cosmic-edit/src/mcp.rs` | Authenticated MCP handlers |
| `native/cosmic-edit/src/claw_glue/ai.rs` | Shared SDK AI requests; document content remains untrusted |
| `native/cosmic-edit/test/unit/mcp.rs` | Handler and UI AI regression with fake OS services |
| `native/test_process.py` | Real binary stdio authentication and service-error coverage |
| `native/PROVENANCE.md` | Fork origins and preserved dependency boundary |

The OS retains filesystem authorization, atomic writes, task-owned inverse
snapshots, desktop execution, AI consent/budget/audit and provider credentials.
Neither UI nor MCP invokes another App. The UI's unsaved buffer goes directly
through the same SDK AI helper as MCP; proposals never write files or memory.
Interactive reload/save and New Window use controlled filesystem and fixed
desktop services instead of the Files/Terminal Apps. Hot-path direct reads
remain inside the common sandbox. A denied save stays unsaved and cannot retry
through App-owned `pkexec`/`tee`; authority and consent stay OS-owned.
The existing git-pinned `cosmic-files` library is a file chooser dependency,
not invocation or migration of the Files App.
The coordinated 0.2.1 GUI requires only owner-relative Home metadata for its
file chooser, with separate protected owner/window browsing consent. Content
read, write and AI are `desktop.optional_needs`, never startup requirements or
a union of MCP grants. Missing optional authority leaves the window available;
opening and saving require independent Root-held file selections rather than
inherited rights or an App-owned permission dialog. Admission neither configures
a model nor grants AI consent/budget. Filesystem declarations are eligibility
bounds, not raw Home mounts or selected content. Native acquisition, atomic-save
adoption and installed display/resource acceptance remain coordinated gates.
Managed file/project/save dialogs start at the SDK owner-home hint instead of
private App-state HOME. An existing document's Save As directory still takes
precedence; configuration and App state remain private.
Existing-file opens that native IO denies queue the SDK's opaque-node read
proposal without blocking the UI. Only Root's `selected` status retries the
native load; pending/denied requests never create a loaded tab or replace a
buffer modified while approval was pending. Reload uses the same native FUSE
boundary, not the scalar filesystem provider. Subprocess fanout is bounded;
no client dialog, status flag or path hint grants access. The production pin
now supplies these 0.2.1 calls. The adapter's existing native tests, real ELF
build and seven-tool process fixture passed against a digest-verified
development archive; actual managed Root selection/rendering and installed UI
acceptance remain pending.
Saving an existing file uses an independent write proposal and the same bounded
nonblocking status path. After selection, native IO writes and syncs only the
Root-reserved scratch name, then renames it over that exact target and syncs its
parent. A status reference is not write authority; Root checks every effect.
The tab's save point advances only after successful native completion, using
the current buffer when approval settles. Changing Save As paths discards the
old status reference. An absent Save As target instead proposes one literal
UTF-8 leaf under its native metadata parent node. After independent Root
approval, it uses the one-shot creation scratch; Root atomically refuses a
racing existing target rather than overwriting it. Creation supplies no read or
overwrite lease, and its status reference is discarded after successful native
completion. Non-UTF8 inverse writes, project watch and installed UI acceptance
remain separate gates.

Build inputs are materialized under `build/editor-native`; SDK/runtime are
resolved only from `platform.lock.json`. The upstream toolkit and rendering
dependency graph in the checked-in native lock is preserved, not replaced by
another product's toolkit patches.

From the repository root on Linux/WSL:

```sh
python3 tools/test.py editor
python3 tools/native_build.py editor test
python3 tools/native_build.py editor build
python3 products/editor/native/test_process.py
```

Rust environment-mutating tests run serially. These fixture checks do not
replace interactive Wayland acceptance.

Native startup uses the shared `claw-app-gui-argv` client helper and the
published SDK's GUI-launch signal to remove only one leading Host `--gui`.
Every remaining argument is a filename, including `--gui` on direct launches
and option-like names or `--`; OS path bytes and order are preserved.
Startup captures these paths in `Flags`, rather than rereading process argv
after GUI initialization. `COS_MCP_SERVER=1` still takes precedence.
The included Rust parser tests use the `cli::tests::` filter.

`native_payload` prepares the real `bin/cosmic-edit` for both signed primary
and MCP entries, preserving resources/licenses. The legacy command enters
`cos app cosmic-edit --gui`; file arguments remain forwarded, not silently
discarded or executed outside the Host. Native argv/resource admission remains
gated as described in [native payloads](../../docs/native-payloads.md).
