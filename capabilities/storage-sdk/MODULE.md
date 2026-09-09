# Storage SDK Shared-Capability Client

This source group owns only the legacy `db` client. It is explicitly
`kind: "shared-capability-client"`, not the Storage business product, a new
installed App, or a copy of an OS SDK/provider. `kv` has not moved.

| Path | Responsibility |
| --- | --- |
| `apps/db/app.json` | Unchanged `db` identity, five MCP/CLI tools and independent database read/write needs |
| `apps/db/main.py` | Existing scoped SQLite CRUD, schema/query, name validation, authorizers and bounded results |
| `apps/db/server.py` | Direct manifest-bound handlers through the immutable OS SDK |
| `apps/db/test_main.py` | SQL/path/policy boundaries, public MCP stdio with the real SDK, transactions, connection lifetime and concurrency |
| `package.json` | Explicit source kind, installed App and test selection; no native assets or library exports |
| `../../tests/test_stage.py` | Exact staged payload, public MCP execution and App-internal refactor cases using only installed platform libraries |

`COS_DATA_DIR` remains the OS-provided owner/App partition. DB files stay at
`$COS_DATA_DIR/db/<database>.db` (normally
`<owner-data>/apps/db/db/<database>.db`). No database is copied, imported or
renamed. KV, Agent memory, credentials, sessions and audit remain separate.
The OS retains App Host/sandbox, identity, grants, policy, SDK/runtime,
privileged services, consent/budgets and signing/install/update authority.
This client invokes no other App.

`query`, `tables` and `schema` require `data.db.read` for the exact database;
`exec` requires only `data.db.write`. Enumeration retains its separate
`data.db.read:*` requirement. Read connections cannot create missing databases
or perform writes, and SQL authorizers refuse cross-database attachment.
Execution remains one statement per committed connection. Queries return at
most 1,000 rows, reporting the full count when truncated. Errors remain
explicit; no source fallback or broader grant is introduced.

## Dependency contracts and independent evolution

The runtime imports only Python's standard library, the SDK's
`claw_os_sdk.mcp.App` (`from_manifest`, `tool`, `serve`), and the OS-bundled
`cos_runtime.policy.require` export. DB uses exact-name and wildcard policy
scopes through the wire-v1 decision transport; it neither implements policy nor
imports the SDK's private dispatcher or any core provider. `cos_runtime` is a
first-party bundled interface, not an independently published third-party SDK.

App-owned unit tests may inspect DB internals. Cross-repository runtime checks
instead start the manifest-declared MCP entrypoint and exchange JSON-RPC over
stdio. The staged tests also rename the private implementation module or the
declared entrypoint in a temporary App payload, preserving tool/grant/data
contracts without changing OS code. SDK internals are not test entrypoints.

A compatible DB implementation change needs no OS core rewrite, and an OS
internal refactor preserving these exports/protocols needs no DB rewrite.
This is not complete source-build or release independence: development still
selects SDK/runtime source directories at the exact `platform.lock.json`
revision; composition consumes `package.json` and `tools/stage.py`; installed
delivery still requires an OS App-pin/package update. Independent runtime
artifacts and a broader compatibility matrix remain outside this migration.
Paired source-cutover commits are migration choreography, not a requirement
to edit both implementations for every future feature.

The four original files came from
[`xiaoyu-work/claw-os` at `7f0e53fa62cbdf46db22ced8747fa04d79081732`](https://github.com/xiaoyu-work/claw-os/tree/7f0e53fa62cbdf46db22ced8747fa04d79081732/apps/db).
The manifest, production implementation and MCP server retain their original
bytes and modes; tests add relocation coverage. First-party attribution and
Apache-2.0 terms remain covered by the identical root [LICENSE](../../LICENSE).

From the repository root on Linux/WSL:

```bash
python3 tools/test.py --capability storage-sdk
python3 tools/test.py files --capability document-engine storage-sdk
python3 tools/stage.py storage-sdk --kind capability --root build/db-stage
```

Tests resolve only `platform.lock.json` libraries, never a sibling OS checkout.
This source move does not establish full boot/upgrade, native visual/hardware
acceptance, or broader backend/identity consolidation.
