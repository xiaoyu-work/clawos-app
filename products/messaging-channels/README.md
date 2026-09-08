# Messaging Channels

Optional channel connectors live here rather than in the OS source tree.
`gateway-discord` is the first relocated connector, preserving its five
operations, matching MCP tools, Discord transport and existing App identity.
`gateway-dingtalk` also lives here: outbound robot send/status with optional
HMAC signing, Markdown, keywords and mentions. It has no inbound Agent loop.
`gateway-googlechat` adds outbound text/cardsV2 and threaded webhook messages;
the configured webhook, not the informational recipient, fixes the destination.

This is a source move, not completion of the connector lifecycle redesign.
Authenticated owner/sender admission and durable replay handling still need
the system-owned connector interface; Discord's legacy `cos agent ask` path is not
newly authorized. No credentials or installed state are copied.

See [MODULE.md](MODULE.md) for boundaries and commands.
