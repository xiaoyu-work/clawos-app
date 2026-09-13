# Files Product

Own the Files MCP operations, argument contract, file metadata behavior and
product tests. The OS owns filesystem authority, sandbox mounts and snapshots.

| Path | Responsibility |
| --- | --- |
| `apps/fs/app.json` | Eighteen MCP tools with exact scopes, object resolvers and declarative effect previews |
| `apps/fs/main.py` | Bounded text/binary IO, metadata, search and file operations |
| `apps/fs/file_plans.py` | Private bounded proposals, real diffs, review fingerprints, durable lifecycle and brokered apply |
| `apps/fs/server.py` | Direct SDK MCP handlers with authenticated snapshot/replacement sessions and structured plan errors |
| `apps/fs/test_main.py`, `apps/fs/test_file_plans.py` | Filesystem, framing, validation, authority and staged-change regressions |
| `apps/docs/app.json` | Four document MCP tools with unchanged Recoll and filesystem scopes |
| `apps/docs/main.py`, `apps/docs/server.py` | Owner-scoped Recoll queries, indexing, status and configuration |
| `apps/docs/test_main.py` | Canonical owner home, subprocess, config and capability regressions |
| `package.json` | Product-owned App staging and test inputs |
| `apps/cosmic-files/` | Seven native MCP tools and authority/staging regressions |
| `native/cosmic-files/` | Complete native UI/library and companion executable, original toolkit graph and resources |
| `native/cosmic-files/src/cli.rs`, `native/cosmic-files/test/unit/cli.rs` | Primary Files argv parsing and path/URI regressions |
| `native/cosmic-files/src/claw_glue/` | Shared product bridge, SDK AI and fixed OS reveal |
| `native/cosmic-files/product_bridge.py` | Private compiled-in adapter over canonical filesystem/Recoll/parser libraries |
| `python/claw_files/document.py` | Named shared descriptor-safe parsing/conversion export, also consumed by the Document Engine capability client |
| `native/test_process.py` | Authenticated real-binary fixture against synthetic OS/model/Recoll services |

The source move preserves `fs` and `docs`, their manifests, runtime behavior
and installed paths. Shared helpers come from App-owned
[`shared/python`](../../shared/MODULE.md); SDK/runtime remain immutable platform
dependencies.
No App-to-App calls or duplicated OS services are introduced. Native source
ownership is complete, but the existing UI hot paths, settings and metadata
remain separate from MCP data. GUI mutations inherit their launch session;
they cannot run from the MCP bridge. The existing `fs` MCP mutation snapshots
continue to use the authenticated per-call context, never process environment.
Filesystem search and its tests require the system `ripgrep` package.
Document search uses the fixed system `recollq` and `recollindex` executables;
its unit tests substitute explicit local executable fixtures. The OS still
owns the background index service and supplies canonical `COS_OWNER_HOME`.
[`Document Engine`](../../capabilities/document-engine/MODULE.md) declares
`claw_files` as a library dependency, not an App call. Doc-only staging includes
the export without installing Files Apps; combined staging checks identical
library content instead of copying conflicting trees. Native Files continues
embedding this same source through its existing native asset declaration.

## Reviewed file plans and object metadata

`fs.plan_write`, `fs.plan_show`, `fs.plan_apply` and `fs.plan_prune` are ordinary
manifest-bound MCP tools, also reached through the existing human CLI command
mapping. Like current `fs.write`, preparation requires explicit text `content`
(which may be empty); it never reads the MCP protocol's stdin. No legacy
`operations`, argv dispatcher or native GUI grant is added.

Preparation reads at most 64 KiB of UTF-8 text and saves a private proposal
under `$COS_DATA_DIR/file-change-plans/<path-sha256>/`. Files use `0600`,
directories `0700`; storage remains within the existing `fs` owner/App
partition. Each target has at most 64 plans, bounded to a 60–86400-second
lifetime. The real unified diff is UTF-8 bounded to 64 KiB. Preparing a
creation neither creates the target nor requires visibility of its parent.
Show requires fresh target read authority before disclosing cached content.

Apply requires an explicit path, plan UUID, exact review digest and
`confirm=true`. Its baseline binds SHA-256, size, device, inode, full mode and
nanosecond modification/change times. After rechecking normal exact read/write
authority and the baseline, it durably records `applying` before snapshot or
replacement. App-owned shared atomic helpers strictly sync records and their
directory entries. Replacement is exclusively the OS public
`system.file.replace` broker via `cos_runtime.file_changes.replace_file`;
neither this App nor its manifest broadens parent mounts to rename a target.
Both snapshot and replacement receive `current_context().session_id`, never
the persistent service's ambient session. Conflicted, consumed and uncertain
plans cannot replay. Confirmed pruning removes only retired private records,
not target files, live drafts or unresolved outcomes.

`objects.file` resolves the ordinary `stat` command (`fs.stat`), and
`objects.change-plan` resolves `plan_show` (`fs.plan_show`) using path identity
and optional plan UUID revision. The canonical `app://fs/TYPE?id=...` reference
is only identity. Schema-only authenticated declarations do not establish
existence, freshness, truth, authority or an available rollback. Effect and
recovery metadata remain previews; a reported snapshot is not OS rollback
evidence.

This source requires the public SDK `claw_os_sdk.objects` reference helpers,
the file-plan wire shape and manifest `objects`/MCP `effects` metadata, plus
the session-aware runtime signature
`replace_file(path, expected, content, *, session_id=...)`. The withdrawn
platform pin is not a compatible release. Validate with an explicitly
versioned, SHA-256-verified development archive through
[the normal platform tooling](../../tools/MODULE.md#local-platform-development);
publication and pin adoption remain coordinated owner decisions. No sibling
OS import or ambient write fallback is supported.

```bash
python3 tools/test.py files
python3 tools/stage.py files --root build/files-stage
python3 tools/native_build.py files test
python3 tools/native_build.py files build
python3 products/files/native/test_process.py
```

The primary native entry uses shared `claw-app-gui-argv` and the published
SDK's GUI-launch signal to remove only the leading Host `--gui`, after the
existing MCP dispatch. Direct `--gui` remains a path; `--` is not a delimiter.
Native flags, config-gated Recents, file-URL canonicalization and the separate
ordered location/URI vectors are unchanged. Non-UTF-8 native path bytes are
preserved. The `cli::tests::` Rust filter exercises the actual parser with
injected canonicalization and a real local file URL. The auxiliary applet
and GIO examples do not use this adaptation.

`native_payload` binds both primary GUI and MCP to the real
`bin/cosmic-files`. App-only preparation also preserves `cosmic-files-applet`
as a signed file; it is not a second declared Host entry. Compatibility
installation therefore refuses that auxiliary surface instead of retaining
an unsandboxed binary or choosing a new identity. See
[native payloads](../../docs/native-payloads.md) for resource and argv gates.
