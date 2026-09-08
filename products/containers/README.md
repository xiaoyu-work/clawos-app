# Containers

The `container-manager` App inspects and controls Docker, rootless/root
Podman and containerd workloads through the OS broker. Its fourteen MCP tools
cover inventory, diagnostics, lifecycle control and confirmed removal.

Source relocation preserves the App identity, runtime choices, exact
observe/control scopes and existing container state. Backend execution and
authority stay in Claw OS; no container daemon is bundled into this product
or accessed directly by the App.

See [MODULE.md](MODULE.md) for source navigation and commands.
