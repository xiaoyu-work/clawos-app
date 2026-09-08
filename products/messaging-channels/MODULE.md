# Messaging Channels

Own optional messaging connector sources: `gateway-discord`, `gateway-dingtalk`,
`gateway-googlechat`, `gateway-larksuite`, `gateway-matrix`, `gateway-mattermost`
and `gateway-rocketchat`.
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
| `package.json` | Product-owned nested staging and tests |

Preserve connector IDs and installed `apps/gateway/<channel>` layouts.
Import the pinned `gateway._shared` namespace, not the unrelated App `_shared`
package or a sibling OS checkout. Shared egress, WebSocket, memory and process
helpers remain platform dependencies. Credential and network authority remain
OS-owned; moving code grants nothing new.

Source relocation preserves the legacy operations adapter, environment/config
precedence, Discord API/resume restrictions and App-scoped
`apps/gateway-discord` state layout. Do not copy credentials, config, cursors,
session identifiers or PID files into this repository. Existing OS state
partition migration remains the authority for installed data.

Discord's legacy inbound path still invokes `cos agent ask`. Local sender allowlists
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

```bash
python3 tools/test.py messaging-channels
python3 tools/stage.py messaging-channels --root build/messaging-channels-stage
```

Tests use temporary state and mocked transport/process boundaries; no real
Discord connection, webhook request, message delivery or Agent task is created.
