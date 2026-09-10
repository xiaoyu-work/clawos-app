# Browser Product

Own the Browser product's search, headless and attached App implementations,
MCP contracts, Chromium extension and Native Messaging host. Native browser
presentation and the reusable engine have not moved.

| Path | Responsibility |
| --- | --- |
| `apps/search/app.json` | Two search tools with explicit provider and exact host/credential scopes |
| `apps/search/main.py` | Google/Brave web and image requests, bounded responses and App memory records |
| `apps/search/server.py` | Direct SDK MCP handlers |
| `apps/search/test_main.py` | Validation, provider isolation, result parsing and failure regressions |
| `apps/web/app.json` | Existing five-operation CLI and matching MCP schemas |
| `apps/web/main.py`, `apps/web/server.py` | Headless reads, scraping, screenshots, forms and gated AI summaries |
| `apps/web/test_main.py` | URL canonicalization, MCP dispatch and existing engine/AI behavior |
| `apps/browser-attached/` | Ten attached-browser MCP tools, Native Host and authority/framing regressions |
| `extension/` | MV3 service worker, top-frame DOM helpers and toolbar popup |
| `packaging/claw-browser-host` | Unprivileged executable selecting the canonical installed Native Host |
| `package.json` | Product-owned staging and test inputs |

Use the immutable platform dependency for SDK/runtime and
[`shared/python`](../../shared/MODULE.md) for credential-client and safe HTTP
helpers. The OS retains secret storage, memory, network authority and
the broker, and the reusable `cos-browser` engine. No App invokes another App; searches never silently switch
provider or borrow an attached browser's login state.

```bash
python3 tools/test.py browser
python3 tools/stage.py browser --root build/browser-stage
```

Product unit tests use synthetic provider responses without live API keys.
OS integration tests exercise the published source through the real worker
sandbox and broker.

The `web` source move preserves its legacy operation-to-MCP adapter and plain
read urllib degradation when the native engine is missing. It does not claim
an MCP-only refactor or native engine migration. Its unit fixtures do not
replace native browser build/rendering acceptance.

`package.json` binds both `installed_assets` to `browser-attached`. The same
staging contract used by the independent `claw-app-browser` Debian package
installs the complete extension at `/usr/share/claw/extensions/claw-agent-browser`
and the executable `/usr/lib/cos/claw-browser-host`. That launcher runs
`/usr/bin/python3 /usr/lib/cos/apps/browser-attached/native_host.py`; only the
canonical App payload owns the implementation. No duplicate is installed under
`/usr/lib/cos/browser-agent`. Canonical `stage.py` invokes the asset helper once;
release assembly does not repeat it. Selecting only Search or Web does not add these
attached-browser assets.

Updating Browser updates its extension, launcher and host together, without a
separate desktop package or Chromium dependency. The OS
`tools/install-browser-agent.sh` only validates installed files and configures
the chosen extension ID, Native Messaging registration and policy. It does not
clone App sources, copy package assets or alter browser profiles. Ordinary
extension/browser reload remains explicit; package upgrades do not kill user
processes or force-install an extension. See
[release ownership and validation](../../docs/releases.md).
`clawd` still owns capabilities, origin injection and privileged socket access.
Package ownership is not a runtime privilege. The direct Native Messaging
launcher/root-peer contract remains subject to the generic authenticated App
Host/session review documented in the release integration blockers.
