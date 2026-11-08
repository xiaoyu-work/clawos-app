# Messaging Channels

The selected messaging connectors are Discord, Telegram, Slack and WhatsApp.
They retain their existing `gateway-discord`, `gateway-telegram`,
`gateway-slack` and `gateway-whatsapp` identities, outbound contracts and account
partitions. The other eleven messaging connectors are removed from source and
package selection; this does not erase previous credentials or installed data.

Managed start/stop/status and confirmed receipt-bound replies use the public
OS SDK. Root verifies Discord/Telegram polling and Slack/WhatsApp signatures,
binds exact owners/senders/accounts, retains replay evidence and wakes existing
bounded Activity triggers. Apps never directly orchestrate Agent work.
Human OS configuration and public HTTPS forwarding for webhooks remain explicit
deployment steps; no credentials or previous installed state are copied.

See [MODULE.md](MODULE.md) for boundaries and commands.
