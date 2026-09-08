# Messaging Channels

Own optional messaging connector sources, starting with `gateway-discord`.
This is a connector ownership group, not another workflow Agent or shared
super-privileged App identity.

| Path | Responsibility |
| --- | --- |
| `apps/gateway/discord/app.json` | Existing configure/send/status/start/stop operations and matching MCP contract |
| `apps/gateway/discord/main.py` | Discord REST/WebSocket transport, allowlists, rate limits, config and resume state |
| `apps/gateway/discord/server.py` | Existing manifest-bound SDK adapter |
| `apps/gateway/discord/test_main.py` | Transport/routing regression tests and real SDK dispatch with synthetic effects |
| `package.json` | Product-owned nested staging and tests |

Preserve `gateway-discord` and installed `apps/gateway/discord` layout.
Import the pinned `gateway._shared` namespace, not the unrelated App `_shared`
package or a sibling OS checkout. Shared egress, WebSocket, memory and process
helpers remain platform dependencies. Credential and network authority remain
OS-owned; moving code grants nothing new.

Source relocation preserves the legacy operations adapter, environment/config
precedence, Discord API/resume restrictions and App-scoped
`apps/gateway-discord` state layout. Do not copy credentials, config, cursors,
session identifiers or PID files into this repository. Existing OS state
partition migration remains the authority for installed data.

The legacy inbound path still invokes `cos agent ask`. Local sender allowlists
and rate limits are not an authenticated owner-bound connector admission API,
and relocation does not make App-originated system-Agent calls authorized.
Service lifecycle, authenticated sender/owner binding and durable replay
handling remain pending. Do not weaken broker restrictions, introduce an
App-to-App route or claim the production inbound loop is accepted by these tests.

```bash
python3 tools/test.py messaging-channels
python3 tools/stage.py messaging-channels --root build/messaging-channels-stage
```

Tests use temporary state and mocked transport/process boundaries; no real
Discord connection, message delivery or Agent task is created.
