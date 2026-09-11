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
and the existing trusted-human elevation flow are unchanged.
The existing git-pinned `cosmic-files` library is a file chooser dependency,
not invocation or migration of the Files App.

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
