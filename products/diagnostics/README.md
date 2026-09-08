# Diagnostics

`hardware-center` exposes nine MCP tools for the system summary, CPU, GPU,
PCI, USB, memory, storage, drivers and thermals. All use the existing named
hardware observation capability through the Claw OS broker.

The App source and interface belong here; privileged collection and
authorization remain OS-owned. This move preserves installed identity and
permissions. `crash-doctor` and `netdiag` remain in Claw OS pending separate
migrations; product grouping must not combine their authority.

See [MODULE.md](MODULE.md) for source navigation and commands.
