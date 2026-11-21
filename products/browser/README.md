# Browser

The `search` App exposes web and image search through an explicitly selected
Google or Brave provider. It loads only that provider's credentials through
the controlled OS interface and records searches through App memory.

The `web` App owns reads, scraping, screenshots, form submission and AI
summaries. The CLI and MCP tools use an isolated Helium renderer through
`clawd`. Each render permits read-only requests to the authorized origin;
cross-origin resources are not loaded. Explicit form submission keeps its
own HTTP and permission path. Summaries still use the SDK AI gate.

`browser-attached` provides ten tools for logged-in Helium tabs. Its Native
Messaging launcher and full MV3 extension source live here too. `clawd` remains
the authority for page origins, secret/eval capabilities and socket access.
The OS manual installer consumes these sources by immutable commit; automatic
extension deployment and updates are not part of this move.

Desktop and headless Helium use the same installed binary but never share
profiles or cookies. The old raw CDP listener is not used. See the [vendored
Helium source and licensing](native/SOURCE.md).

See [MODULE.md](MODULE.md) for source navigation and product commands.
