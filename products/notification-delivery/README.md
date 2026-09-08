# Notification Delivery

Own optional notification/event delivery connector sources, starting with
`gateway-ntfy`. This is not another notification service or chat Agent.
`gateway-pushover` and `gateway-webhook` remain pending their separate moves.

The ntfy App exposes one-shot send/status, metadata headers and explicit,
stored or anonymous authentication. The manifest requires `server` for both
operations; its URL determines network authority. Legacy direct Python calls
retain their default server behavior. Stored tokens are not sent to the public
default `https://ntfy.sh`; explicit authentication remains caller-controlled.

The OS Notification Service separately owns durable records, owner isolation,
DND, deduplication, leases, retries and acknowledgements. Its Rust ntfy adapter
and deterministic dispatcher stay in `claw-os` and do not call this App.
Source relocation does not connect this one-shot path to that queue, add a
database or claim end-to-end durable delivery. Any later integration must use
the existing service contract, not duplicate its state machine.

See [MODULE.md](MODULE.md) for local contracts and commands.
