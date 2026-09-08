# Terminal Product

Own the existing `exec` App implementation and process-operation contract.
The OS owns process authority and sandbox enforcement. Native Terminal UI
and shared terminal-session integration have not moved or been consolidated.

| Path | Responsibility |
| --- | --- |
| `apps/exec/app.json` | Six CLI operations and matching MCP tools |
| `apps/exec/main.py` | Bounded capture, script invocation and background process registry |
| `apps/exec/server.py` | Existing manifest operation-to-MCP adapter |
| `apps/exec/test_main.py` | Scratch isolation, shell scope, execution and service regressions |
| `package.json` | Product-owned staging and test inputs |

The source move preserves identity, capability declarations, output shapes
and `COS_DATA_DIR/proc` state. Shared environment scrubbing and atomic writes
come from the pinned OS libraries. No App-to-App invocation is introduced.
This is not an MCP-only redesign or a replacement for the OS process service.

```bash
python3 tools/test.py terminal
python3 tools/stage.py terminal --root build/terminal-stage
```

Run on Linux/WSL. Background-process tests use mock processes and temporary
registries; the direct execution regression runs a short-lived Python child.
