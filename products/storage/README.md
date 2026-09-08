# Storage

`storage-manager` exposes six MCP tools for device inventory, health,
read-only filesystem checks, mounting, unmounting and safe ejection.
It preserves separate observation/diagnostic permissions and exact-device
mount authority.

UDisks2 execution, block-device validation and no-repair checkers remain
behind the Claw OS broker. Existing mounted data, installed App identity and
permissions do not change. This is storage management, not a shared database
interface for other products.

See [MODULE.md](MODULE.md) for source navigation and commands.
