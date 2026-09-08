# Diagnostics Product

Own `hardware-center`'s nine hardware inventory tools, `crash-doctor`'s
three crash inspection tools and `netdiag`'s five network diagnostic tools.
The product groups diagnostic interfaces, not their permissions or OS providers.

| Path | Responsibility |
| --- | --- |
| `apps/hardware-center/app.json` | Nine tools with the exact named hardware observation scope |
| `apps/hardware-center/main.py` | Validated `cos __hardware` broker requests and structured results |
| `apps/hardware-center/server.py` | Direct SDK MCP handlers |
| `apps/hardware-center/test_main.py` | Scope/argv contracts, all SDK routes and broker failures |
| `apps/crash-doctor/app.json` | Sensitive crash scope, bounded queries and coredump selector |
| `apps/crash-doctor/main.py`, `server.py` | Validated `cos __crash` requests and direct SDK MCP handlers |
| `apps/crash-doctor/test_main.py` | Bounds/ID validation, error propagation and real SDK dispatch |
| `apps/netdiag/app.json` | Network observation and exact target resolution/probe needs |
| `apps/netdiag/main.py`, `server.py` | Validated bounded requests through the private network diagnostics runtime bridge |
| `apps/netdiag/test_main.py` | Target/port/budget validation, SDK defaults and all diagnostic routes |
| `package.json` | Product-owned staging and test inputs |

Preserve the `hardware-center` installed identity and `sys.observe` scope
`hardware`. The OS provider authenticates that App identity and owns hardware
collection, kernel interfaces and external inventory tools. Relocation neither
adds raw device access nor broadens permissions. No hardware database or OS
service implementation is copied into this product.

`crash-doctor` keeps its separate installed identity and `sys.crash` scope
`system`. Coredumps, journal access, correlation and constrained debugger
execution remain behind the OS crash provider. Source relocation does not copy
crash data or let hardware observation grants authorize crash inspection.

`netdiag` retains its installed identity and separate network observation,
resolution and probe scopes. It has no direct sockets or host network access.
The OS owns interface/route collection, bounded DNS resolution and DNS-pinned
TCP probes. TCP diagnosis requires an explicit port and a bounded probe
budget; neither product grouping nor source relocation relaxes these limits.

```bash
python3 tools/test.py diagnostics
python3 tools/stage.py diagnostics --root build/diagnostics-stage
```

Tests use synthetic diagnostic responses, not host inspection or network probes.
