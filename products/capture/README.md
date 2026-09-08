# Capture

Capture owns the complete `cosmic-screenshot` native portal client, its MCP
surface, translations, icons, desktop entry and original build/debian inputs.
Its installed identities remain `cosmic-screenshot` and `com.clawos.Screenshot`.

The original UI is supplied by the OS screenshot portal, not a libcosmic
window inside this crate. Native launch still opens that same interactive
region/window/output chooser, with the same destination/clipboard choices
and optional localized notification. The shared portal/compositor, clipboard
execution, session authority and portal configuration remain OS-owned.

Non-interactive CLI and MCP use the same typed OS service. The OS starts only
this product's fixed native portal pipe mode in the authenticated owner's
session, bounds capture/output, and persists a non-overwriting `0600` PNG in
the exact authorized directory with OS task snapshots. There are no Files,
execution or notification App calls. Existing XDG Pictures and portal-selected
paths remain in place; no images, configuration or user state are imported.

MCP requires `desktop.capture:screen` separately from `fs.write:save_dir`;
the new screen grant needs explicit consent and uses the existing Settings
revocation system. It grants neither clipboard access nor generic native
launch. `interactive=true` is human-only and is rejected before any MCP
service call. The App Host resolves the existing `~/Pictures` default to the
owner's absolute path; a worker never substitutes its private HOME.

See [MODULE.md](MODULE.md) for commands and [PROVENANCE.md](PROVENANCE.md) for
source/license details. Source relocation does not complete the broader
product/data/visual redesign or establish interactive Wayland acceptance.
