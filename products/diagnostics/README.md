# Diagnostics

`hardware-center` exposes nine MCP tools for the system summary, CPU, GPU,
PCI, USB, memory, storage, drivers and thermals. All use the existing named
hardware observation capability through the Claw OS broker.

`crash-doctor` exposes recent crashes, diagnosis and backtrace tools through
the separate sensitive crash capability. Query bounds, defaults and canonical
coredump IDs are preserved; journal/coredump access and debugger execution
remain OS-owned.

`netdiag` exposes interface, route, DNS, TCP and staged diagnosis tools.
Its private runtime bridge delegates to the OS network provider without
opening sockets in the App. Exact target scopes, explicit TCP ports and probe
budgets remain enforced.

The App source and interface belong here; privileged collection and
authorization remain OS-owned. These source moves preserve installed identities
and permissions; product grouping must not combine diagnostic authority.

See [MODULE.md](MODULE.md) for source navigation and commands.
