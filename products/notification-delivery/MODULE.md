# Notification Delivery Module

## Responsibility

Own optional delivery App sources without owning notification policy or state.
Preserve App identities, nested installed paths and separate grants.

| Path | Role |
| --- | --- |
| `apps/gateway/ntfy/app.json` | Send/status, required server, URL-derived host and conditional stored-token scope |
| `apps/gateway/ntfy/main.py` | One-shot UTF-8 publish, topic/auth selection, metadata and status |
| `apps/gateway/ntfy/server.py` | Existing manifest-bound SDK adapter |
| `apps/gateway/ntfy/test_main.py` | Direct/SDK dispatch and migrated gateway argument/auth regressions |
| `package.json` | Product-owned payload staging and tests |

## Boundaries

Import `gateway._shared` from the pinned platform dependency, never a sibling
OS checkout or the unrelated App `_shared` package. Credentials, host-gated
egress, package signing and installed authority stay OS-owned.

The ntfy manifest requires a server for send/status. Do not infer that its old
docstring's server-resolution description is the current launch contract.
The source move preserves this requirement, optional topic lookup, explicit
bearer-before-basic precedence and stored-token suppression for the public
default server. It does not broaden network grants or copy account state.

The platform's `core/src/notifications/` service and Rust ntfy adapter remain
separate from this one-shot App. Notification records, DND, leases, retries,
owner isolation and acknowledgements belong there. A future adapter integration
must use that service; no App-to-App route or second delivery queue belongs here.

## Validation

```bash
python3 tools/test.py notification-delivery
python3 tools/stage.py notification-delivery --root build/notification-delivery-stage
```

Tests mock all external transport and credentials. They do not send real
notifications or demonstrate a durable service-to-App delivery integration.
