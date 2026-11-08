# Messaging Channels

Own the four selected connectors: `gateway-discord`, `gateway-telegram`,
`gateway-slack` and `gateway-whatsapp`. This group is not another workflow Agent
or a shared super-privileged identity. The other eleven messaging connectors
remain retired; previous credentials and installed data are not deleted.
Notification Delivery and Home Integration remain separate products.

| Path | Responsibility |
| --- | --- |
| `apps/gateway/<platform>/main.py` | Existing outbound provider client and presentation for managed channel operations |
| `apps/gateway/<platform>/app.json` | Product-local operation/MCP arguments, permissions and installed identity |
| `apps/gateway/<platform>/server.py` | Existing manifest-bound SDK adapter |
| `apps/gateway/<platform>/test_main.py` | Retained outbound/config regression contracts with synthetic transport |
| `test_channels.py` | Four-platform direct/MCP lifecycle, confirmed receipt-bound reply and refusal tests |
| `../../shared/python/gateway/_shared/channels.py` | Presentation-only public SDK client; no credentials, receiver or task authority |

## System-owned ingress

The OS owns authenticated owner/provider/sender configuration, credential
custody, receiver lifetime, cursors, rate limits, durable replay and reply
receipts. Apps call the versioned SDK `channels.control`; they never call
`cos agent ask`, manage receiver processes, choose an owner/source or submit
Agent tasks. There is no local-process fallback if `clawd` is unavailable.
Import App client support through `gateway._shared`, not a sibling OS checkout.

A human first creates a bounded Activity and an ordinary generation-bound
trigger matching `channel:gateway-<platform>` and `message.received`. Protected
`cos channels configure <platform>` binds one exact sender/channel and the
provider account to that owned trigger. It verifies the owner's fixed
credentials and requires normal scheduler consent. Enabling ingress cannot
create a trigger or grant Agent authority.

Discord uses bounded authenticated REST history polling for an exact
DM/guild/thread channel. Telegram uses authenticated Bot API polling, with a
separate sender ID even in a group. Initial activation establishes an inert
latest-message baseline; it is not historical backlog replay. Message-content
and channel/history provider access must already be enabled. Telegram requires
exclusive use of that bot's polling cursor.

Slack verifies exact raw-body HMAC, request freshness and workspace/App IDs.
WhatsApp verifies raw-body HMAC, GET verify-token handshake and business-account/
phone-number IDs. Both need operator-owned public HTTPS forwarding to the
Root receiver's loopback route. Only ordinary text messages are admitted; bot
messages, edits, attachments and delivery-status callbacks are not Agent requests.

Each `status`, `start`, `stop` and `reply` operation declares only its exact
`ipc.publish:Name(channel:gateway-<platform>)` OS control surface. Inbound
credentials and network work belong to the human-configured OS receiver, not
the App's transient MCP permission union. Obsolete App `agent.spawn` and local
process-lifecycle needs are removed. Existing outbound send needs remain intact.

`reply` takes only a verified `event_id`, repeatable text and required
`confirm=true`. Root resolves the original owned account/recipient/thread,
checks the current binding and reply window, and retains an in-flight record
before provider submission. Uncertain submissions never automatically resend.
WhatsApp BSUID recipients retain the entire opaque identifier; no phone number
is invented. A provider submission ID is not delivery confirmation.

Root reports admitted messages in the existing owner-visible context journal
and wakes ordinary Activity triggers/Jobs. Message content remains fenced
untrusted data, not an owner-authored workflow instruction. Stop prevents new
admission, not cancellation or rollback of already-published Jobs/requests.
Status discloses pending evidence and errors. Corruption, uncertain progress and
retained capacity limits hold work rather than resetting or replaying it.

## Compatibility and acceptance

The four identities, installed `apps/gateway/<platform>` layouts and existing
account partitions are unchanged. Discord's App-local `configure` preferences
are retained and explicitly labelled as non-authoritative; they do not silently
become Root admission configuration. Old Discord/Telegram PID/cursor/session
files are neither read by the managed receiver nor migrated/deleted.

Outbound clients retain credential/environment precedence, provider endpoints,
limits, error reporting and self-memory recording. Discord still splits
messages and disables mentions; Telegram keeps repeatable text/truncation;
Slack retains API-level failure handling; WhatsApp legacy `send` keeps its
phone-number contract while verified BSUID replies use the OS receipt path.

```bash
python3 tools/test.py messaging-channels
python3 tools/stage.py messaging-channels --root build/messaging-channels-stage
```

Tests use isolated synthetic public SDK/MCP interfaces, provider responses and
temporary state, never live accounts, messages or paid models. OS coverage
tests signatures, owner separation, replay, Activity Job admission and
indeterminate reply refusal. Source contracts need the matching published
SDK/runtime and installed OS/App packages; headless tests do not accept public
HTTPS deployment, native UI or live provider delivery.
