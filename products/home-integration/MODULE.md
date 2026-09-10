# Home Integration Module

## Responsibility

Own the `gateway-homeassistant` REST integration source, not the external Home
Assistant server, its UI, device registry or automation engine. Installed App
identity, nested layout and operation grants are unchanged by relocation.

| Path | Role |
| --- | --- |
| `apps/gateway/homeassistant/app.json` | Send/call/status arguments and existing capability declarations |
| `apps/gateway/homeassistant/main.py` | Notify payloads, JSON service calls, configuration and response handling |
| `apps/gateway/homeassistant/server.py` | Manifest-bound SDK adapter |
| `apps/gateway/homeassistant/test_main.py` | Direct/SDK dispatch, validation, credentials and egress boundaries |
| `package.json` | Product-owned payload staging and tests |

## Contracts and Boundaries

`send` requires service and text; `notify` expands to `notify.notify`, but
omitting service does not select a default. Other domains use `call`, whose
manifest takes JSON text that must decode to an object. Legacy direct Python
calls also accept a dictionary payload. `status` reports configuration, not
server reachability; it exposes the configured base URL but not the token.

The existing wildcard network declaration, two exact secret grants and
send-only self-memory grant remain separate. Service success is not a promise
that a device has reached the requested state. No device event subscription,
state polling, local automation store or App-to-App orchestration is added.

Use `gateway._shared.gateway_args` for canonical list dispatch so flags before
`--` cannot displace the service/message positionals. Unknown flags and excess
positionals are rejected; do not restore the old index-based parser.

Import `gateway._shared` from App-owned [`shared/python`](../../shared/MODULE.md),
staged in the separate common runtime at `/usr/lib/cos/python`.
OS credential access, capability policy, host-gated egress,
signing and installation remain OS-owned. Do not bypass the shared default
private-address block to make local Home Assistant endpoints reachable.
Deployment network authorization is separate from this source move.

## Validation

```bash
python3 tools/test.py home-integration
python3 tools/stage.py home-integration --root build/home-integration-stage
```

Tests use synthetic configuration and mocked transports. They never connect
to Home Assistant or operate real devices.
