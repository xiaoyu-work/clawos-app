# Store

The `pkg` App searches and inspects the local apt catalog, reports installed
packages and submits package changes to the Claw OS broker. Its thirteen
existing CLI operations and MCP tools keep their identities, arguments and
permissions.

Privileged package execution, transaction serialization, audit and rollback
remain OS-owned. This move does not alter the installed package database or
APT update mechanism.

The native `cosmic-store` UI is still in Claw OS. Moving its launcher alone,
or retaining its legacy App-to-App forwarding, would not complete the Store
product integration.

See [MODULE.md](MODULE.md) for source navigation and commands.
