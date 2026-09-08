# Diagnostics Product

Own `hardware-center`'s nine hardware inventory tools and `crash-doctor`'s
three crash inspection tools. Network diagnostics (`netdiag`) await migration.
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

```bash
python3 tools/test.py diagnostics
python3 tools/stage.py diagnostics --root build/diagnostics-stage
```

Tests use synthetic inventory and crash responses rather than inspecting the host.
