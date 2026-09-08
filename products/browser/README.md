# Browser

The `search` App exposes web and image search through an explicitly selected
Google or Brave provider. It loads only that provider's credentials through
the controlled OS interface and records searches through App memory.

The `web` App owns headless reads, scraping, screenshots, form submission and
AI summaries. Its existing CLI/operation-to-MCP contract is preserved, along
with the plain-read urllib path when the native engine is absent. The
`cos-browser` engine and its system dependencies remain OS-owned; summaries
still use the SDK AI gate.

`browser-attached` provides ten tools for logged-in Chromium tabs. Its Native
Messaging host and full MV3 extension source live here too. `clawd` remains
the authority for page origins, secret/eval capabilities and socket access.
The OS manual installer consumes these sources by immutable commit; automatic
extension deployment and updates are not part of this move.

This source migration preserves App identities, installed paths and capability
scopes. It does not consolidate browser sessions or move the native browser UI.
Headless and attached logged-in sessions remain separate authority boundaries.

See [MODULE.md](MODULE.md) for source navigation and product commands.
