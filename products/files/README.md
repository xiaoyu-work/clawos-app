# Files

The existing `fs` App provides eighteen direct SDK MCP tools for filesystem
operations, bounded text/binary reads, metadata and search. Mutation snapshots
use the authenticated MCP session, and the manifest owns the capability schema.
Its four reviewed file-plan tools prepare private bounded UTF-8 drafts and real
diffs, then apply explicitly confirmed review fingerprints through exact OS
file authority. Preparation never writes a target; uncertain applies cannot
replay. Object references and effect/recovery declarations are metadata, not
existence, permission or rollback guarantees. See
[the plan contract and platform requirements](MODULE.md#reviewed-file-plans-and-object-metadata).

The `docs` App adds four MCP tools for Recoll document search, indexing, status
and configuration. It uses the owner's existing `~/.recoll` state, with
`COS_OWNER_HOME` supplied by the OS host rather than the service's private home.
Recoll remains an external system dependency; its background index service is
OS-owned. The product does not duplicate that service or add semantic search.

The complete native `cosmic-files` UI, file-chooser library and
`cosmic-files-applet` companion now live under `native/cosmic-files`.
Their source, assets, localization, licenses and original locked toolkit
graph are preserved. UI and MCP share embedded filesystem/Recoll business
libraries, shared multi-format document parsing and the SDK AI gate, never
another App. Native reveal uses the OS's fixed `com.clawos.Files` target.
Metadata explicitly requires the sibling tag directory read scope; summary
memory uses only `self:cosmic-files`, not another App's namespace.

The shared parser is staged into the Agent package as `claw_files.document`
for the remaining Document App too. Native binaries embed it at build time.
SDK/runtime libraries are system-owned and no mutable product script is
loaded at runtime. Existing native hot-path file operations, thumbnail caches,
and settings are not consolidated with MCP metadata. Recoll still owns its
existing index. The three installed identities and their grants remain
separate; this move does not migrate user data or claim visual acceptance.

```bash
python3 tools/test.py files
python3 tools/native_build.py files test
python3 tools/native_build.py files build
python3 products/files/native/test_process.py
```

The native runner selects the two workspace packages in separate Cargo calls,
matching the upstream justfile without unifying the companion's
`desktop-applet` feature into the main Files executable.
The process fixture requires Linux `bubblewrap` and substitutes all OS/model/
Recoll services using synthetic repository-local files. It does not launch a
desktop session. The native workspace build includes both executables.

See [MODULE.md](MODULE.md) for source navigation and commands. Development
depends on the pinned OS SDK/runtime and shared libraries, not a sibling checkout.
Search also requires the `rg` executable (`sudo apt-get install ripgrep` on
Debian/Ubuntu), including when running the product's search regressions.
