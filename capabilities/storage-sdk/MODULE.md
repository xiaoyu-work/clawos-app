# Storage SDK Shared-Capability Client

This source group owns the legacy `db` and `kv` clients. It is explicitly
`kind: "shared-capability-client"`, not the Storage business product, a new
installed App, or a copy of an OS SDK/provider. The two clients retain separate
identities, grants and data; KV is not Agent memory.

| Path | Responsibility |
| --- | --- |
| `apps/db/app.json` | Unchanged `db` identity, five MCP/CLI tools and independent database read/write needs |
| `apps/db/main.py` | Existing scoped SQLite CRUD, schema/query, name validation, authorizers and bounded results |
| `apps/db/server.py` | Direct manifest-bound handlers through the immutable OS SDK |
| `apps/db/test_main.py` | SQL/path/policy boundaries, public MCP stdio with the real SDK, transactions, connection lifetime and concurrency |
| `apps/kv/app.json` | Five unchanged tool/CLI schemas and separate exact-key read/write/delete needs |
| `apps/kv/server.py` | Complete KV MCP, strict UTF-8 string-map persistence, parsed cache, flock and atomic replacement; no `main.py` |
| `apps/kv/test_server.py` | Original tests plus isolated cache/locking/failure/privacy and real MCP process regressions |
| `package.json` | Explicit source kind, installed App and test selection; no native assets or library exports |
| `../../tests/test_stage.py` | Exact staged payload, public MCP execution and App-internal refactor cases using only installed platform libraries |

`COS_DATA_DIR` remains the OS-provided owner/App partition. DB files stay at
`$COS_DATA_DIR/db/<database>.db` (normally
`<owner-data>/apps/db/db/<database>.db`). No database is copied, imported or
renamed. KV keeps `$COS_DATA_DIR/kv.json` and its `kv.json.lock` sibling
(normally `<owner-data>/apps/kv/kv.json`). It does not import or merge DB,
Storage Manager, Agent memory, credentials, sessions or audit state.
The OS retains App Host/sandbox, identity, grants, policy, SDK/runtime,
privileged services, consent/budgets and signing/install/update authority.
Neither client invokes another App.

`query`, `tables` and `schema` require `data.db.read` for the exact database;
`exec` requires only `data.db.write`. Enumeration retains its separate
`data.db.read:*` requirement. Read connections cannot create missing databases
or perform writes, and SQL authorizers refuse cross-database attachment.
Execution remains one statement per committed connection. Queries return at
most 1,000 rows, reporting the full count when truncated. Errors remain
explicit; no source fallback or broader grant is introduced.

KV preserves `get`'s empty-string missing result, string keys/values, idempotent
`del`, sorted `fnmatch` filtering with default `pattern="*"`, and the existing
set/list/dump object shapes. `get`, `set` and `del` require respectively
`data.kv.read`, `data.kv.write` and `data.kv.delete` on the exact key.
List and dump now explicitly require the existing whole-store read scope
through a fixed wildcard binding. The old `kind: "wild"` borrowed a caller's
named-key grants, which cannot safely authorize an unfiltered store scan.
A pattern does not narrow the required grant, and no union of key grants
becomes full-store authority. The OS gates every call before forwarding it. KV does not add
duplicate in-handler authorization or a read/write/delete grant union.

Relocation also fixes demonstrated persistence bugs: cached reads now compare
the current bytes before reusing parsed JSON; mutations hold one exclusive
flock across read-modify-replace; threads serialize cache publication; failed
commits cannot publish uncommitted cache values. Atomic writes and new lock
files explicitly request mode `0600`. Missing stores remain empty without a
read-side file creation; corrupt, non-object, non-string or invalid UTF-8
stores fail explicitly, including after a cache has warmed. No repair,
replay or user-data transition is introduced.

## Dependency contracts and independent evolution

DB imports only Python's standard library, the SDK's
`claw_os_sdk.mcp.App` (`from_manifest`, `tool`, `serve`), and the OS-bundled
`cos_runtime.policy.require` export. DB uses exact-name and wildcard policy
scopes through the wire-v1 decision transport; it neither implements policy nor
imports the SDK's private dispatcher or any core provider. `cos_runtime` is a
first-party bundled interface, not an independently published third-party SDK.
KV uses the existing OS-owned `_shared.atomic.atomic_write_bytes` export,
already selected by `platform.lock.json` and placed on the installed MCP
Python path by the OS. The server does not adjust `sys.path` or depend on a
sibling source directory. No SDK/runtime or atomic helper is copied into the
capability payload, and no platform-lock bump is needed.

App-owned unit tests may inspect their own client internals. Cross-repository runtime checks
instead start the manifest-declared MCP entrypoint and exchange JSON-RPC over
stdio. The staged tests also rename the private implementation module or the
declared entrypoint in a temporary App payload, preserving tool/grant/data
contracts without changing OS code. KV has equivalent module/entrypoint
refactor cases. SDK internals are not test entrypoints. Standalone SDK tests
do not replace the OS's capability-denial and signed-worker checks.

A compatible client implementation change needs no OS core rewrite, and an OS
internal refactor preserving these exports/protocols needs no client rewrite.
This is not complete source-build or release independence: development still
selects SDK/runtime source directories at the exact `platform.lock.json`
revision; composition consumes `package.json` and `tools/stage.py`; installed
delivery still requires an OS App-pin/package update. Independent runtime
artifacts and a broader compatibility matrix remain outside this migration.
Paired source-cutover commits are migration choreography, not a requirement
to edit both implementations for every future feature.

DB's four original files came from
[`xiaoyu-work/claw-os` at `7f0e53fa62cbdf46db22ced8747fa04d79081732`](https://github.com/xiaoyu-work/claw-os/tree/7f0e53fa62cbdf46db22ced8747fa04d79081732/apps/db).
The manifest, production implementation and MCP server retain their original
bytes and modes; tests add relocation coverage. First-party attribution and
Apache-2.0 terms remain covered by the identical root [LICENSE](../../LICENSE).
KV's three original files came from
[`xiaoyu-work/claw-os` at `2ade4720c0667601d2675a189c61ab08992e185d`](https://github.com/xiaoyu-work/claw-os/tree/2ade4720c0667601d2675a189c61ab08992e185d/apps/kv)
under the same license. Its runtime fixes are described above. The manifest
corrects stale Agent-memory wording and the two whole-store authorization
bindings using the existing fixed-scope contract. Identity, version, tool/CLI
arguments, stored grants and state paths are retained; no permission is
automatically added or widened.

From the repository root on Linux/WSL:

```bash
python3 tools/test.py --capability storage-sdk
python3 tools/test.py files --capability document-engine storage-sdk
python3 tools/stage.py storage-sdk --kind capability --root build/storage-sdk-stage
python3 tools/stage.py storage-sdk --kind capability --apps kv --root build/kv-stage
```

Tests resolve only `platform.lock.json` libraries, never a sibling OS checkout.
`package.json` explicitly selects KV's `test_server.py`; neither a production
`main.py` nor a placeholder `test_main.py` is required or created.
This source move does not establish full boot/upgrade, native visual/hardware
acceptance, or broader backend/identity consolidation.
