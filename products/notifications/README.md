# Notifications

This product owns the complete native `cosmic-notifications` Layer Shell
daemon, MCP, configuration/util libraries and original build/provenance inputs,
plus the complete Python `notify` facade and its tests.
The installed binary remains `/usr/bin/cosmic-notifications` in
`claw-os-desktop`, with identity `com.clawos.Notifications`.

Normal UI and MCP share the existing **OS durable Notification Service**
through its single desktop delivery consumer. MCP submits bounded intent using
the versioned SDK and fixed `/usr/local/bin/cos`; it does not open a session bus,
call another App or maintain a second notification store.

## Native MCP 0.2 compatibility

- `notify.post` retains summary/body, sender label, theme icon, timeout and
  transient fields, and adds optional owner/source-scoped `dedupe_key`.
- It returns a durable `notif-` string ID. `notify.close` accepts only a string
  returned to the same authenticated App/owner. Old desktop integer IDs are
  explicitly unsupported; there is no persistent alias table.
- A sender label is never producer identity. Absolute/file/URL icon paths are
  explicitly unsupported without file authority.
- `expire_ms` is -1/default, 0/forever, or positive signed 32-bit milliseconds.
  It controls popup presentation, not durable activity retention.
- `transient` omits the desktop history copy, never authoritative OS history.
  Delivery success and popup expiry are not user acknowledgement.
- Both tools retain the existing `ui.notify` Wild consent rationale. There is
  no owner-wide list/preferences/acknowledgement or other-App close authority.

Native freedesktop compatibility remains: each sender owns its numeric handles,
while the human panel uses its existing private connection for dismissal.
The OS desktop bridge verifies the installed presenter's owner/executable and
unique connection, renders model content as plain text, and reflects durable
close/acknowledgement. Existing native DND remains an additional presentation
mute; core DND/delivery preferences remain authoritative.
Retired popup-history entries release their numeric handles without
acknowledgement. The bridge opts its own presentations into connection-bound
lifetime, so disconnect/crash closes orphaned popups without altering durable
state. Ordinary freedesktop clients do not opt in and keep their original
lifetime. The hint affects only its authenticated sender's presentations,
never another sender or any core record.

The full original 40-file fork plus the new presentation/tests is retained:
standalone lock, nested crates, `.cargo`, Debian/Nix/hook/just/build metadata,
upstream files and GPL license. This fork had no standalone icon or locale
directory. Cross-shell session startup and panel resources remain OS-owned.
`native_libraries` explicitly exports the two shared presentation crates for
immutable OS consumers; no duplicate vendored library is maintained.

## Legacy `notify` 0.2 compatibility

`apps/notify` now owns both MCP-only commands and the same human CLI aliases:
`cos app notify send MESSAGE [--urgent]` and `cos app notify list [--limit N]`.
They use the shared SDK's fixed installed-binary, cancellable stdin transport.
The App does not open a bus/database, invoke the native App, claim deliveries,
or maintain a JSON/SQLite/ID-alias store.

- `notify.send(message, urgent=false)` requires the existing `ui.notify` Wild
  grant. Message is 1..4000 plain-text Unicode characters; unsupported controls
  are rejected (newline/CR/tab remain allowed). There is no truncation.
  Urgent maps to warning severity; both modes use normal Immediate delivery
  subject to DND/channel preferences, never the critical DND bypass.
- Send still returns `{id,message,urgent,timestamp}`. The ID is now a durable
  `notif-...` string, not eight characters. Timestamp is UTC creation time to
  seconds, without a suffix. Source is authenticated `app:notify`, never text
  supplied by the model; owner/task/session come from broker authority.
- `notify.list(limit=20)` independently requires `data.inbox.read` Wild.
  Limit is integer 1..100, never a boolean. It exposes only the same owner's
  `app:notify` records, not native, task or other-App producers.
  `{notifications,total}` is newest publication first, with the complete
  retained, unexpired source total even when the returned batch is limited.
  Rows retain `read` and add `state`; read means the state is not unread
  (read/acknowledged/dismissed). Delivery alone leaves it false.
- Native post/close remain native-only; neither identity gains the other's
  actions or grants. The native App cannot close a guessed notify-produced ID.

**Historical JSON is preserved in place, not imported.** The old
`notifications.json` is not read, rewritten, deleted, moved, re-owned, chmodded,
dual-written, backfilled or replayed, even if malformed or obsolete.
It is explicitly excluded from new lists. No archive browser or importer is
added, and service failure is an MCP error, never JSON or empty-list fallback.
Only new OS-service records persist across App/service restart.

The old filename was relative to the actual launcher `COS_DATA_DIR`, not
universally `/var/lib/cos`: a worker gets `<data-root>/apps/notify`, ordinarily
under `~/.local/share/cos` or a configured owner root; an App service Host uses
its private `<host-control>/data` root before partitioning. Older unpartitioned
files may remain directly under their original root. The OS no longer
automatically moves notify's old file at launch. This transition never searches
these locations or extends the ordinary lifetime of ephemeral Host namespaces.

See [MODULE.md](MODULE.md) for exact tests and [PROVENANCE.md](PROVENANCE.md) for
origins. Source ownership and new service persistence do not merge old history,
identities, settings or grants. Headless tests do not establish interactive
visual/full-image acceptance.
