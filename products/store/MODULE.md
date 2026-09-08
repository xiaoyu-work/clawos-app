# Store Product

Own the `pkg` App's thirteen existing CLI operations and matching MCP adapter.
The native `cosmic-store` UI remains in Claw OS pending its complete source,
build and service integration migration; its legacy App forwarding is not
the product's target interface.

| Path | Responsibility |
| --- | --- |
| `apps/pkg/app.json` | CLI/MCP arguments and existing package/observation capabilities |
| `apps/pkg/main.py` | Read-only apt/dpkg queries and `cos __package` mutation requests |
| `apps/pkg/server.py` | Runtime adapter from manifest operations to SDK MCP |
| `apps/pkg/test_main.py` | Catalog parsing, validation, scoped broker requests and all MCP operation routes |
| `package.json` | Product-owned staging and test inputs |

Preserve the installed `pkg` identity and existing permissions. The OS package
provider requires that identity, serializes transactions and records mutation
and rollback state. No installed package database, apt configuration or OS
provider code moves into this repository. Product code never invokes another
App, and the GUI must not gain authority by forwarding through `pkg`.

```bash
python3 tools/test.py store
python3 tools/stage.py store --root build/store-stage
```

Tests mock package queries and mutations; they do not install or remove software.
