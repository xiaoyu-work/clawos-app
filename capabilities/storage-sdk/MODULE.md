# Storage SDK Shared-Capability Client

This source group owns only the legacy `db` client. It is explicitly
`kind: "shared-capability-client"`, not the Storage business product, a new
installed App, or a copy of an OS SDK/provider. `kv` has not moved.

| Path | Responsibility |
| --- | --- |
| `apps/db/app.json` | Unchanged `db` identity, five MCP/CLI tools and independent database read/write needs |
| `apps/db/main.py` | Existing scoped SQLite CRUD, schema/query, name validation, authorizers and bounded results |
| `apps/db/server.py` | Direct manifest-bound handlers through the immutable OS SDK |
| `apps/db/test_main.py` | SQL/path/policy boundaries, real SDK dispatch, transactions, connection lifetime and concurrency |
| `package.json` | Explicit source kind, installed App and test selection; no native assets or library exports |
| `../../tests/test_stage.py` | Exact staged payload and real SDK execution using only installed platform libraries |

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
