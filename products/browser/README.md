# Browser

The `search` App exposes web and image search through an explicitly selected
Google or Brave provider. It loads only that provider's credentials through
the controlled OS interface and records searches through App memory.

This source migration preserves the `search` identity, installed path, two
MCP tools and existing capability scopes. It does not consolidate browser
sessions or move the native browser UI, `web` or `browser-attached` yet.
Headless and attached logged-in sessions remain separate authority boundaries.

See [MODULE.md](MODULE.md) for source navigation and product commands.
