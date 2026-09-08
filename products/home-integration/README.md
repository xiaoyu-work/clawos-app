# Home Integration

Own the existing `gateway-homeassistant` App source independently of Claw OS.
This is a device/service integration, not a chat connector, a new GUI or a
copy of the Home Assistant upstream server.

`send` calls notify services with message/title; `call` posts a JSON object
to a named REST service; `status` reports local configuration. Home Assistant
remains an externally configured server. Its token, accounts, device state
and automations are not copied or migrated into this product.

Existing grants and shared OS egress checks are preserved, including the
default private-address block. Source relocation does not authorize access
to a LAN endpoint, add event subscriptions or confirm physical device state.
Cross-product orchestration remains the responsibility of the system Agent.

See [MODULE.md](MODULE.md) for contracts and commands.
