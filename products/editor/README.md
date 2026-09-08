# Text Editor

The complete native Claw OS Text Editor now lives in this product:
`cosmic-edit`, its UI, seven MCP tools, localization, resources and packaging.
Installed identity `/usr/bin/cosmic-edit` / `com.clawos.Edit` is unchanged.

See [MODULE.md](MODULE.md) for ownership and validation, and
[native/PROVENANCE.md](native/PROVENANCE.md) for upstream licensing.
OS desktop packages consume an immutable source revision; no source cache,
credentials, user documents or editor settings are shipped by this move.

The interactive AI actions and MCP AI tools share the gated SDK helper as
`cosmic-edit`, with strict safety, `external-content` origin and the existing
200,000-unit monthly budget. Interactive requests operate on the unsaved
buffer; file-based MCP requests retain controlled bounded reads. Summaries,
explanations and replacement proposals do not silently save files or memory.
