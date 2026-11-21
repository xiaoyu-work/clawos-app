# Browser Product

Own the Browser product's search, headless and attached App implementations,
MCP contracts, Helium-compatible extension and Native Messaging launchers.
The [vendored Helium source](native/SOURCE.md) is distinct from the installed
upstream `helium-bin` runtime.

| Path | Responsibility |
| --- | --- |
| `apps/search/app.json` | Two search tools with explicit provider and exact host/credential scopes |
| `apps/search/main.py` | Google/Brave web and image requests, bounded responses and App memory records |
| `apps/search/server.py` | Direct SDK MCP handlers |
| `apps/search/test_main.py` | Validation, provider isolation, result parsing and failure regressions |
| `apps/web/app.json` | Existing five-operation CLI and matching MCP schemas |
| `apps/web/main.py`, `apps/web/server.py` | Headless reads, scraping, screenshots, forms and gated AI summaries |
| `apps/web/test_main.py` | URL canonicalization, MCP dispatch and existing engine/AI behavior |
| `apps/browser-attached/` | Ten attached-browser MCP tools and a compatibility launcher for the OS transport |
| `extension/` | MV3 service worker, top-frame DOM helpers and native browser chat side panel |
| `packaging/claw-browser-host` | Unprivileged executable selecting the versioned OS browser transport |
| `package.json` | Product-owned staging and test inputs |

Use the immutable platform dependency for SDK/runtime and
[`shared/python`](../../shared/MODULE.md) for credential-client and safe HTTP
helpers. The OS retains secret storage, memory, network authority and
the renderer process. No App invokes another App; searches never silently switch
provider or borrow an attached browser's login state.

```bash
python3 tools/test.py browser
python3 tools/stage.py browser --root build/browser-stage
```

Product unit tests use synthetic provider responses without live API keys.
OS integration tests exercise the published source through the real worker
sandbox and broker.

The `web` App uses the existing runtime bridge to send a typed render request
to `clawd`. No browser socket, display, profile or direct network access
enters the App worker. A missing renderer fails explicitly. Screenshots
create a new PNG at an approved output path; form submissions keep the
separately approved HTTP path.

`package.json` binds both `installed_assets` to `browser-attached`. The same
staging contract used by the independent `claw-app-browser` Debian package
installs the complete extension at `/usr/share/claw/extensions/claw-agent-browser`
and the executable `/usr/lib/cos/claw-browser-host`. That launcher selects the
OS-owned `/usr/lib/cos/browser-native-host.py` with isolated system Python.
The old package-local `native_host.py` is only a compatibility launcher, not a
socket server or authority implementation. `claw-os-browser-bridge-v1 (= 1)`
is an Agent service dependency, not an installed App identity or grant.
No duplicate transport is installed under `/usr/lib/cos/browser-agent`.
Canonical `stage.py` invokes the asset helper once;
release assembly does not repeat it. Selecting only Search or Web does not add these
attached-browser assets.

Updating Browser updates its extension and launchers together. The App package
depends on the signed upstream Helium runtime and the matching OS renderer. The OS
`tools/install-browser-agent.sh` only validates installed files and configures
the chosen extension ID, Native Messaging registration and policy. It does not
clone App sources, copy package assets or alter browser profiles. Ordinary
extension/browser reload remains explicit; package upgrades do not kill user
processes or force-install an extension. See
[release ownership and validation](../../docs/releases.md).
`clawd` owns capabilities, origin injection and privileged socket access.
Its OS transport retains owner-only runtime/socket validation, kernel Root-peer
admission, bounded Native Messaging frames and response correlation. It is
system transport, not another App entrypoint or an exemption from App hosting.
Every attached-browser tool still uses its ordinary authenticated App Host and
own exact grants. Live installed browser/extension acceptance remains separate
from source, unit and package checks.

The side panel uses a separate OS-owned Native Messaging host in the Desktop
package for the existing Claw Agent. Its opt-in tab context contains only the
tab ID and origin; the panel does not read page bodies, cookies, or model
credentials. Browser package upgrades do not require Desktop for MCP or CLI.
