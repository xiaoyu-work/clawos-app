# Security Product

Own `security-center`'s seven sensitive read-only MCP tools. `firewall-manager`
and `usb-guard` await their individual migrations into this product.

| Path | Responsibility |
| --- | --- |
| `apps/security-center/app.json` | Sensitive `sys.security:audit` grant for all seven tools |
| `apps/security-center/main.py` | Typed `cos __security` broker client; no direct privileged inspection |
| `apps/security-center/server.py` | Direct SDK handlers for summary/auth/ssh/sudo/mac/ports/events |
| `apps/security-center/test_main.py` | Direct/SDK routes, exact scopes/argv and broker errors |
| `package.json` | Product-owned staging and test inputs |

Preserve the installed `security-center` identity and its dedicated sensitive
read grant. Read-only security evidence is not ordinary `sys.observe` access.
The OS owns journal/configuration inspection, privileged command execution,
report generation and authorization. Do not copy security journals or settings
into this repository.

Product grouping does not combine security inspection, firewall control and
USB authorization. Their providers and permission boundaries remain separate.
Apps do not call one another or bypass the broker.

```bash
python3 tools/test.py security
python3 tools/stage.py security --root build/security-stage
```

Tests use synthetic broker responses, not live system security evidence.
