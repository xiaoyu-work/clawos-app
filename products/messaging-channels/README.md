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

This is a source move, not completion of the connector lifecycle redesign.
Authenticated owner/sender admission and durable replay handling still need
the system-owned connector interface; Discord's legacy `cos agent ask` path is not
newly authorized. No credentials or installed state are copied.

See [MODULE.md](MODULE.md) for boundaries and commands.
