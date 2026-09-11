# Terminal Product

Own the complete native Terminal UI and the existing `exec` App implementation.
The OS owns process authority, sandbox enforcement, filesystem snapshots and
fixed native desktop activation. Interactive PTYs and the `exec` process
registry remain separate; this source move does not consolidate sessions.

| Path | Responsibility |
| --- | --- |
| `apps/exec/app.json` | Six CLI operations and matching MCP tools |
| `apps/exec/main.py` | Bounded capture, script invocation and background process registry |
| `apps/exec/server.py` | Existing manifest operation-to-MCP adapter |
| `apps/exec/test_main.py` | Scratch isolation, shell scope, execution and service regressions |
| `apps/cosmic-term/` | Native descriptor and independent three-tool/grant contracts |
| `native/cosmic-term/` | Full terminal renderer, PTYs, configuration, resources, packaging and tests |
| `native/cosmic-term/src/cli.rs`, `native/cosmic-term/test/unit/cli.rs` | Native option/command parsing and bounded GUI argv regressions |
| `native/cosmic-term/src/product.rs` | Compiled-in shared command adapter and controlled OS filesystem/desktop clients |
| `native/test_process.py` | Real authenticated stdio binary with isolated command and OS-service fixtures |
| `package.json` | Product-owned staging and test inputs |

The source move preserves identity, capability declarations, output shapes
and `COS_DATA_DIR/proc` state. Shared environment scrubbing and atomic writes
come from App-owned [`shared/python`](../../shared/MODULE.md), staged separately
from the pinned OS SDK/runtime. No App-to-App invocation is introduced.
Native MCP embeds the canonical `exec` command implementation as a private
library, not an App call; it uses only bounded run and PATH lookup, never the
background registry. The worker's authenticated broker session stays intact:
caller metadata never replaces it or manufactures snapshot authority. Command
children retain environment scrubbing and the native Host sandbox/grants.

UI state writes use controlled filesystem snapshots with separately authorized
missing parents. MCP cannot use the human UI write adapter. New Window and
`term.open` use the fixed OS Terminal target under the existing
`proc.spawn:cosmic-term` grant, not a widened desktop capability.
Ask Claw's bounded anonymous context transport, existing configurable
shell Copilot integration, PTY startup, renderer fallback and password-manager
integration are retained. No credentials, histories or user state are moved.

```bash
python3 tools/test.py terminal
python3 tools/stage.py terminal --root build/terminal-stage
python3 tools/native_build.py terminal test
python3 tools/native_build.py terminal build
python3 products/terminal/native/test_process.py
```

Run on Linux/WSL. Background-process tests use mock processes and temporary
registries; the direct execution regression runs a short-lived Python child.
Native process tests require bubblewrap and use synthetic broker/command
executables, never an interactive shell, GUI or live keyring. `just install`
in the generated native tree retains upstream desktop/icon/metainfo paths.
Native builds require the paired OS's fixed Terminal desktop service at runtime.

Native startup uses shared `claw-app-gui-argv` with the published SDK's
GUI-launch signal, removing only one leading Host `--gui` after MCP dispatch.
The native parser still handles argv0, help/version early exits, working-directory
values, unknown-argument warnings and daemonization as before. `-e`, `--command`
and `--` stop option scanning; every suffix token stays in the command,
including `--gui` and option-like values. Working-directory OS bytes are
preserved; shell strings retain the existing terminal backend conversion.
The included Rust parser regressions use the `cli::tests::` filter.

The native payload now selects one real `bin/cosmic-term` for primary GUI and
MCP, with original resources/licenses in the App snapshot. Its legacy command
routes through `cos app cosmic-term --gui`, preserving argument boundaries and
Host errors. PTY, argument and resource acceptance remains separate; see
[native payloads](../../docs/native-payloads.md).
