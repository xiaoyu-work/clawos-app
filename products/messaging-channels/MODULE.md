# Messaging Channels

Own optional messaging connector sources: `gateway-discord`, `gateway-dingtalk`,
`gateway-googlechat`, `gateway-larksuite`, `gateway-matrix`, `gateway-mattermost`,
`gateway-rocketchat`, `gateway-signal`, `gateway-slack`, `gateway-sms`, `gateway-teams`,
`gateway-telegram`, `gateway-webex`, `gateway-whatsapp` and `gateway-zulip`.
This is a connector ownership group, not another workflow Agent or shared
super-privileged App identity.

| Path | Responsibility |
| --- | --- |
| `apps/gateway/discord/app.json` | Existing configure/send/status/start/stop operations and matching MCP contract |
| `apps/gateway/discord/main.py` | Discord REST/WebSocket transport, allowlists, rate limits, config and resume state |
| `apps/gateway/discord/server.py` | Existing manifest-bound SDK adapter |
| `apps/gateway/discord/test_main.py` | Transport/routing regression tests and real SDK dispatch with synthetic effects |
| `apps/gateway/dingtalk/` | Outbound robot send/status, HMAC signing, Markdown/keyword/mentions and direct/SDK tests |
| `apps/gateway/googlechat/` | Outbound webhook send/status, text/cardsV2, thread queries and direct/SDK tests |
| `apps/gateway/larksuite/` | Outbound text/rich-post/card send/status and official custom-bot HMAC signing |
| `apps/gateway/matrix/` | Outbound room messages, escaped room IDs, transaction IDs and send/status SDK contracts |
| `apps/gateway/mattermost/` | Outbound webhook send/status, channel/DM and username/icon overrides |
| `apps/gateway/rocketchat/` | REST send/status, channel/DM targets and separate token/user-id headers |
| `apps/gateway/signal/` | External signal-cli-rest-api send/status, recipient normalization and group routing |
| `apps/gateway/slack/` | Web API send/status, bot-token authentication and API-level error handling |
| `apps/gateway/sms/` | Twilio send/status, form encoding and phone/Messaging Service sender selection |
| `apps/gateway/teams/` | Fixed-destination webhook, Adaptive Card and explicit legacy MessageCard send/status |
| `apps/gateway/telegram/` | Bot API send/status/start/stop, legacy polling, offset/PID state and allowlist/rate-limit tests |
| `apps/gateway/webex/` | REST send/status, email/room routing and Markdown/plain-text payloads |
| `apps/gateway/whatsapp/` | Cloud API send/status, sender phone-number ID and recipient normalization |
| `apps/gateway/zulip/` | Realm send/status, stream/topic and private-email routing with API-level results |
| `package.json` | Product-owned nested staging and tests |

Preserve connector IDs and installed `apps/gateway/<channel>` layouts.
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

DingTalk is outbound-only, with no inbound Agent loop or local state store.
Keep its existing operations adapter, optional signing and environment/credential
precedence. Its manifest retains the existing wildcard network grant; the shared
egress helper still checks the actual destination host. This move does not narrow
or expand consent, add retries/delivery leases or change webhook policy.

Google Chat is also outbound-only and keeps its operations adapter and existing
network/credential/memory grants. The webhook fixes the space; `recipient` is
informational and never retargets a request. Thread keys retain the existing
reply-or-create behavior. No local state or notification delivery service is added.

Lark/Feishu retains send/status, optional signing, card-over-post precedence and
the existing grants. Its migration corrects the old signing algorithm:
HMAC-SHA256 uses `timestamp + "\n" + secret` as the key and an empty message,
then base64-encodes the result; timestamps are seconds. See the
[official custom-bot guide](https://open.larksuite.com/document/client-docs/bot-v3/add-custom-bot).
Known-answer tests cover the signer and all three message shapes through MCP.
Unsigned mode remains available as before; no credential or state migration occurs.

Matrix preserves send/status and existing grants, including its environment/
credential homeserver selection and existing default. It sends `m.text` through
the Client-Server API, escapes the room ID as one path segment and generates a
transaction ID per send. There is no local state store or inbound `/sync` loop;
source relocation does not add either or establish a durable delivery lifecycle.

Mattermost preserves send/status and existing grants. Unlike Google Chat,
`recipient` becomes the webhook payload's `channel` and can select a channel
name or `@handle`; omission leaves the webhook default in place. Username/icon
overrides remain payload fields, not separately fetched resources. No inbound
endpoint, local state store or new delivery lifecycle is introduced.

Rocket.Chat retains REST `chat.postMessage` send/status with channel names,
`#channels` and `@handles` passed unchanged. Its site/user-id/token credentials
and environment precedence remain separate, with the existing exact secret
grants and shared host-gated egress. No inbound service or local state is added.

Signal preserves its `/v2/send` client, phone normalization, group-ID heuristic
and existing grants/base-URL selection. `signal-cli-rest-api` remains an external
dependency; account pairing and service state are not copied or staged here.
The default local endpoint does not grant private-network access: shared egress
restrictions remain enforced, without automatically enabling a bypass.
Inbound `/v1/receive` polling remains unimplemented.

Slack keeps `chat.postMessage` send/status, token environment precedence, text
truncation and API-level failure reporting even on HTTP success. The manifest's
existing Slack-host, exact credential and self-memory grants remain unchanged;
status needs no credentials or network. Socket Mode and Events HTTP remain
unimplemented, with no new service lifecycle or state store.

SMS preserves the Twilio Messages REST client, Basic authentication,
phone normalization and mutually exclusive `From`/`MessagingServiceSid` fields.
Its existing Twilio-host, three exact credential and self-memory grants remain
unchanged. Unlike Slack, status reads configuration credentials but never
returns the account SID or auth token. No inbound webhook or delivery callback
is implemented; a queued API response is not proof of SMS delivery.

Teams preserves Adaptive Card v1.5 by default and explicit legacy MessageCard
selection, not automatic fallback. Its recipient flag is informational; the
configured webhook fixes the destination. Existing wildcard network, exact
credential and self-memory grants remain unchanged, with actual host checks
in shared egress. No inbound service, delivery lifecycle or state store is added.

Telegram retains four operations and its repeatable-text send contract.
Direct/SDK tests use synthetic transport, subprocesses and signals with temporary
offset/PID files; they do not establish that App-originated Agent dispatch is
authorized. Existing polling, allowlists, rate limits and grants are preserved,
not upgraded into authenticated owner-bound admission or durable delivery.

Webex preserves email-to-`toPersonEmail` routing and sends other recipients as
`roomId`, with Markdown plus text by default or text alone for `plain`.
Despite its legacy manifest/docstring wording, person-ID autodetection is not
implemented. Source relocation does not add it, inbound webhooks or local state.
Existing Webex-host, exact credential and self-memory grants remain unchanged.

WhatsApp preserves Graph API v21.0, separate sender phone-number ID and token,
recipient digit normalization, text truncation and disabled URL previews.
Its existing Graph-host, exact credential and self-memory grants are unchanged;
status reads no credentials and performs no network request. Webhook reception
and delivery confirmation remain unimplemented; a message ID is not a receipt.

Zulip preserves stream/topic addressing, the existing empty-topic default,
single/group email private messages and form encoding with Basic authentication.
Only an API `result=success` reports success. Existing wildcard network, three
exact credentials and self-memory grants remain unchanged; shared egress checks
the actual realm host. No inbound event loop or local state store is introduced.

```bash
python3 tools/test.py messaging-channels
python3 tools/stage.py messaging-channels --root build/messaging-channels-stage
```

Tests use temporary state and mocked transport/process boundaries; no real
Discord connection, webhook request, message delivery or Agent task is created.
