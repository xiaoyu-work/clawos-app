# Settings Product

Own `accessibility-manager`'s five MCP tools for status, screen reader,
magnifier, inversion and color filters. Native `cosmic-settings` and other
system-management Apps await their individual migrations.

| Path | Responsibility |
| --- | --- |
| `apps/accessibility-manager/app.json` | Separate observation/control scopes and closed toggle/filter choices |
| `apps/accessibility-manager/main.py` | Validated `cos __accessibility` requests |
| `apps/accessibility-manager/server.py` | Direct SDK MCP handlers |
| `apps/accessibility-manager/test_main.py` | All SDK routes/choices, exact scopes and pre-policy validation |
| `package.json` | Product-owned staging and test inputs |

Preserve the installed App identity. Status requires `sys.observe` scope
`accessibility`; mutations require `ui.accessibility` scope `control`.
The OS owns user-session validation, Wayland helper execution, AT-SPI state
changes and serialization. Existing accessibility state does not move.

Settings organizes interfaces, not a union of authority. Each provider must
retain its own App identity, scope checks and consent boundary. Apps do not
call one another; moving a native launcher alone is not a complete UI migration.

```bash
python3 tools/test.py settings
python3 tools/stage.py settings --root build/settings-stage
```

Tests use synthetic broker responses and do not change desktop accessibility.
