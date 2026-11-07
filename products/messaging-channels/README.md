# Messaging Channels

The selected messaging connectors are Discord, Telegram, Slack and WhatsApp.
They retain their existing `gateway-discord`, `gateway-telegram`,
`gateway-slack` and `gateway-whatsapp` identities, MCP contracts and account
partitions. The other eleven messaging connectors are removed from source and
package selection; this does not erase previous credentials or installed data.

Discord and Telegram retain their legacy receive transports. Slack and
WhatsApp retain their outbound API clients. Formal authenticated inbound
admission, supervised lifecycle and durable replay handling remain OS-owned
integration work, not an App-originated Agent bypass.

This is a source move, not completion of the connector lifecycle redesign.
Authenticated owner/sender admission and durable replay handling still need
the system-owned connector interface; Discord and Telegram legacy `cos agent ask` paths are not
newly authorized. No credentials or installed state are copied.

See [MODULE.md](MODULE.md) for boundaries and commands.
