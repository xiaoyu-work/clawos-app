# Editor Product

Own the complete `cosmic-edit` native UI, MCP handlers, AI presentation,
resources, translations, build inputs and descriptor.

| Path | Responsibility |
| --- | --- |
| `apps/cosmic-edit/app.json` | Seven tools, exact file scopes, fixed desktop launch and AI budget |
| `native/cosmic-edit/src/main.rs` | Native editor UI and unsaved-buffer AI requests |
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
