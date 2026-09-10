# HTTP Shared-Capability Client

This source group owns the complete legacy `net` client, not another business
product or an OS networking provider. `package.json` explicitly declares
`kind: "shared-capability-client"`.

| Path | Responsibility |
| --- | --- |
| `apps/net/app.json` | Unchanged `net` identity, two MCP/CLI tools, argument bindings and exact needs |
| `apps/net/main.py` | Request validation, headers, bounded responses and private atomic downloads |
| `apps/net/server.py` | Manifest-bound public SDK MCP entrypoint |
| `apps/net/test_main.py` | Existing validation, response-bound, failure and output-preservation regressions |
| `apps/net/test_mcp.py` | Staged public MCP contracts over the OS CONNECT transport, including compatible internal refactors |
| `package.json` | Explicit source kind, App ownership and test selection |

`net.fetch` keeps its GET/POST/PUT/DELETE methods, repeatable headers, optional
data and 1..300-second timeout. Requests are bounded to 1,000,000 data bytes;
responses retain at most 5,000,000 bytes and report truncation. `net.download`
requires an explicit canonical output path, retains its 512 MiB default limit
(`COS_NET_DOWNLOAD_MAX`), and fails rather than publishing a partial download.
The old destination survives network, size-limit, flush and replacement
failures. Existing CLI bindings, response shapes and grants are unchanged.

The App consumes the App-owned [`_shared.safe_http`](../../shared/MODULE.md)
export. That library owns
URL/IDNA normalization, exact host-and-port authorization on every redirect,
DNS screening, brokered transport and TLS peer verification. The App separately
requests `fs.write` for the exact download output. SDK/runtime, worker isolation,
privileged egress enforcement, credentials, audit, signing and installation
remain in `claw-os`. No provider implementation, other App handler, local
database or user state is copied into this group.

Development resolves SDK/runtime through `platform.lock.json` and
`tools/platform_dependency.py`, and `_shared` from local `shared/python`.
Installed execution uses `/usr/lib/cos/python`: the common App runtime owns
the helper, separately from OS SDK/runtime. The client has no parent-directory
import shim. There are no runtime source downloads or alternate App
implementations when the declared dependency is unavailable.

Cross-repository consumers use MCP stdio and the manifest's entrypoint, not
private SDK dispatch or HTTP implementation modules. Fixtures exercise a local
Unix CONNECT peer without reaching the public network, including redirect
authorization, denial, broker refusal, bounded downloads and module/entrypoint
renames. Existing unit coverage retains the detailed size and cleanup cases.
Immutable source exports and OS signed-package delivery remain explicit build
and release dependencies; source relocation alone does not establish fully
independent distribution.

From the repository root on Linux/WSL:

```bash
python3 tools/test.py --capability http
python3 tools/stage.py http --kind capability --root build/http-stage
```

First-party source remains covered by the repository root license. This move
does not grant new permissions, replace the OS provider, retire `net`, or claim
live image/upgrade acceptance.
