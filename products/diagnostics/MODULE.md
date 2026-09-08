# Diagnostics Product

Own the `hardware-center` App's nine MCP hardware inventory tools. Crash and
network diagnostics (`crash-doctor`, `netdiag`) await their own migrations.
The product groups diagnostic interfaces, not their permissions or OS providers.

| Path | Responsibility |
| --- | --- |
| `apps/hardware-center/app.json` | Nine tools with the exact named hardware observation scope |
| `apps/hardware-center/main.py` | Validated `cos __hardware` broker requests and structured results |
| `apps/hardware-center/server.py` | Direct SDK MCP handlers |
| `apps/hardware-center/test_main.py` | Scope/argv contracts, all SDK routes and broker failures |
| `package.json` | Product-owned staging and test inputs |

Preserve the `hardware-center` installed identity and `sys.observe` scope
`hardware`. The OS provider authenticates that App identity and owns hardware
collection, kernel interfaces and external inventory tools. Relocation neither
adds raw device access nor broadens permissions. No hardware database or OS
service implementation is copied into this product.

```bash
python3 tools/test.py diagnostics
python3 tools/stage.py diagnostics --root build/diagnostics-stage
```

Tests use synthetic inventory responses rather than inspecting the host.
