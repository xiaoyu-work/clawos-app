# Containers Product

Own the `container-manager` App's fourteen typed MCP tools and container
management contract. The OS owns runtime execution, peer/App authorization,
privilege separation, mutation serialization and process/network isolation.

| Path | Responsibility |
| --- | --- |
| `apps/container-manager/app.json` | Runtime choices, namespace condition, confirmation and observe/control scopes |
| `apps/container-manager/main.py` | Validated requests to the existing `cos __container` broker interface |
| `apps/container-manager/server.py` | Direct SDK MCP handlers |
| `apps/container-manager/test_main.py` | Fourteen routes, exact argv/scopes, validation and broker failures |
| `package.json` | Product-owned staging and test inputs |

Preserve the installed `container-manager` identity: the OS provider binds
authority to it. Runtime selection stays explicit; `podman` and `podman-root`
remain separate choices, and containerd requires a namespace. Removal requires
explicit confirmation. No runtime socket, root capability or another App is
used as a substitute for the broker.

```bash
python3 tools/test.py containers
python3 tools/stage.py containers --root build/containers-stage
```

Tests use synthetic broker responses; they do not mutate live containers.
The product has a CLI/MCP interface; a new GUI is not required for this move.
