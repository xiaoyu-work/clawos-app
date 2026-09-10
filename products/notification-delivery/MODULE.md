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
| `apps/gateway/pushover/` | One-shot send/status, user/group key overrides, emergency options and API results |
| `apps/gateway/webhook/` | JSON/raw POST, target/default credentials, authentication and egress regressions |
| `package.json` | Product-owned payload staging and tests |

## Boundaries

Import `gateway._shared` from App-owned [`shared/python`](../../shared/MODULE.md),
staged once in the common runtime, never a sibling OS checkout or the unrelated
`_shared` namespace. Credentials, host-gated
egress, package signing and installed authority stay OS-owned.

The ntfy manifest requires a server for send/status. Do not infer that its old
docstring's server-resolution description is the current launch contract.
The source move preserves this requirement, optional topic lookup, explicit
bearer-before-basic precedence and stored-token suppression for the public
default server. It does not broaden network grants or copy account state.

Pushover retains its exact API host, two credential grants and self-memory scope.
`recipient` is an optional flag, not a positional argument as the old docstring
suggests. Emergency `retry`/`expire` fields are remote Pushover behavior, not a
local delivery queue. Returning a receipt identifier does not poll or confirm
acknowledgement. No DND, retry state or credentials are copied into this product.

Webhook retains its existing wildcard network declaration, two exact secret
grants and self-memory scope; runtime egress still enforces host policy and
blocks private endpoints/redirects. The target is a flag or configured default,
not a leading positional. Authentication precedence is bearer, then basic,
then API key; HMAC signing is independent and can accompany any of them.
These are the implementation contracts, not the older docstring's
last-option-wins claim. HTTP and HTTPS are both accepted. No incoming webhook,
retry queue or durable delivery integration is added by relocation.

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
