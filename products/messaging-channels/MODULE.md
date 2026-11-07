# Messaging Channels

Own the four selected messaging connectors: `gateway-discord`, `gateway-slack`,
`gateway-telegram` and `gateway-whatsapp`.
This is a connector ownership group, not another workflow Agent or shared
super-privileged App identity.

| Path | Responsibility |
| --- | --- |
| `apps/gateway/discord/app.json` | Existing configure/send/status/start/stop operations and matching MCP contract |
| `apps/gateway/discord/main.py` | Discord REST/WebSocket transport, allowlists, rate limits, config and resume state |
| `apps/gateway/discord/server.py` | Existing manifest-bound SDK adapter |
| `apps/gateway/discord/test_main.py` | Transport/routing regression tests and real SDK dispatch with synthetic effects |
| `apps/gateway/slack/` | Web API send/status, bot-token authentication and API-level error handling |
| `apps/gateway/telegram/` | Bot API send/status/start/stop, legacy polling, offset/PID state and allowlist/rate-limit tests |
| `apps/gateway/whatsapp/` | Cloud API send/status, sender phone-number ID and recipient normalization |
| `package.json` | Product-owned nested staging and tests |

Preserve the four retained IDs and installed `apps/gateway/<channel>` layouts.
The other eleven messaging connectors are explicitly retired from source and
package selection. Their previous credentials and installed state are not
deleted or migrated by this source change. Notification Delivery and Home
Integration are separate products and remain selected.
Import the App-owned `gateway._shared` namespace from
[`shared/python`](../../shared/MODULE.md), not the unrelated `_shared` namespace
or a sibling OS checkout. Shared egress, WebSocket, memory and process helpers
ship once in the App common runtime at `/usr/lib/cos/python`. Credential and
network authority remain OS-owned; moving code grants nothing new.

Source relocation preserves the legacy operations adapter, environment/config
precedence, Discord API/resume restrictions and App-scoped
`apps/gateway-discord` state layout. Telegram retains `apps/gateway-telegram`
offset/PID state and its existing OS partition migration. Do not copy credentials, config, cursors,
session identifiers or PID files into this repository. Existing OS state
partition migration remains the authority for installed data.

Discord and Telegram legacy inbound paths still invoke `cos agent ask`. Local sender allowlists
and rate limits are not an authenticated owner-bound connector admission API,
and relocation does not make App-originated system-Agent calls authorized.
Service lifecycle, authenticated sender/owner binding and durable replay
handling remain pending. Do not weaken broker restrictions, introduce an
App-to-App route or claim the production inbound loop is accepted by these tests.

Slack keeps `chat.postMessage` send/status, token environment precedence, text
truncation and API-level failure reporting even on HTTP success. The manifest's
existing Slack-host, exact credential and self-memory grants remain unchanged;
status needs no credentials or network. Socket Mode and Events HTTP remain
unimplemented, with no new service lifecycle or state store.

Telegram retains four operations and its repeatable-text send contract.
Direct/SDK tests use synthetic transport, subprocesses and signals with temporary
offset/PID files; they do not establish that App-originated Agent dispatch is
authorized. Existing polling, allowlists, rate limits and grants are preserved,
not upgraded into authenticated owner-bound admission or durable delivery.

WhatsApp preserves Graph API v21.0, separate sender phone-number ID and token,
recipient digit normalization, text truncation and disabled URL previews.
Its existing Graph-host, exact credential and self-memory grants are unchanged;
status reads no credentials and performs no network request. Webhook reception
and delivery confirmation remain unimplemented; a message ID is not a receipt.

```bash
python3 tools/test.py messaging-channels
python3 tools/stage.py messaging-channels --root build/messaging-channels-stage
```

Tests use temporary state and mocked transport/process boundaries; no real
Discord connection, webhook request, message delivery or Agent task is created.
