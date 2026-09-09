# Notifications

This product owns the complete native `cosmic-notifications` Layer Shell
daemon, MCP, configuration/util libraries and original build/provenance inputs.
The installed binary remains `/usr/bin/cosmic-notifications` in
`claw-os-desktop`, with identity `com.clawos.Notifications`.

Normal UI and MCP share the existing **OS durable Notification Service**
through its single desktop delivery consumer. MCP submits bounded intent using
the versioned SDK and fixed `/usr/local/bin/cos`; it does not open a session bus,
call another App or maintain a second notification store.

## MCP 0.2 compatibility

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

See [MODULE.md](MODULE.md) for exact tests and [PROVENANCE.md](PROVENANCE.md) for
origins. **Legacy `notify` remains in `claw-os` with its existing JSON history.**
Its explicit state transition is the next identity, not part of this source
move. No user data, settings, identities or grants are consolidated here, and
headless tests do not establish interactive visual/full-image acceptance.
