# Messaging Channels

Optional channel connectors live here rather than in the OS source tree.
`gateway-discord` is the first relocated connector, preserving its five
operations, matching MCP tools, Discord transport and existing App identity.
`gateway-dingtalk` also lives here: outbound robot send/status with optional
HMAC signing, Markdown, keywords and mentions. It has no inbound Agent loop.
`gateway-googlechat` adds outbound text/cardsV2 and threaded webhook messages;
the configured webhook, not the informational recipient, fixes the destination.
`gateway-larksuite` owns Lark/Feishu text, rich posts and interactive cards.
Its signing implementation is corrected to the official custom-bot algorithm;
existing optional signing and permissions are preserved.
`gateway-matrix` sends room text through the Client-Server API and reports
status. Its `/sync` inbound loop remains unimplemented.
`gateway-mattermost` preserves outgoing webhook messages with optional
channel/DM, username and icon overrides; inbound endpoints remain out of scope.
`gateway-rocketchat` sends through REST `chat.postMessage` with separate token
and user-id headers, retaining channel/DM targets and configuration status.
`gateway-signal` is the outbound client for an external `signal-cli-rest-api`
service. Phone/group handling remains intact; account state, inbound polling
and private-network authorization are not supplied by this source relocation.
`gateway-slack` keeps Web API `chat.postMessage` and status, bot-token
authentication and API error reporting. Socket Mode / Events HTTP remain
unimplemented; relocation adds no inbound service or state store.
`gateway-sms` owns the Twilio send/status client with phone or Messaging Service
sender selection. Credentials remain OS-owned; inbound webhooks and delivery
confirmation are not provided by this move.
`gateway-teams` keeps default Adaptive Cards and explicit legacy MessageCards.
The webhook fixes the destination; `recipient` is informational and does not
retarget messages. No automatic fallback or inbound service is added.
`gateway-telegram` includes send/status/start/stop and the legacy long-poll loop,
with repeatable message text, allowlist/rate limiting and offset/PID state.
Account credentials and installed state are not copied; OS partition migration
remains responsible for existing data.

This is a source move, not completion of the connector lifecycle redesign.
Authenticated owner/sender admission and durable replay handling still need
the system-owned connector interface; Discord and Telegram legacy `cos agent ask` paths are not
newly authorized. No credentials or installed state are copied.

See [MODULE.md](MODULE.md) for boundaries and commands.
