# Files

The existing `fs` App provides fourteen direct SDK MCP tools for filesystem
operations, bounded text/binary reads, metadata and search. Mutation snapshots
use the authenticated MCP session, and the manifest owns the capability schema.

Repository relocation does not change the App ID, installed path, filesystem
permissions, snapshots or runtime behavior. This is the operation-side source
move, not a completed native Files UI/backend consolidation.

See [MODULE.md](MODULE.md) for source navigation and commands. Development
depends on the pinned OS SDK/runtime and shared libraries, not a sibling checkout.
Search also requires the `rg` executable (`sudo apt-get install ripgrep` on
Debian/Ubuntu), including when running the product's search regressions.
