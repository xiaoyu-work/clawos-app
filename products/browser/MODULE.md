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
| `package.json` | Product-owned staging and test inputs |

Use the immutable platform dependency for SDK/runtime, credentials and safe
HTTP helpers. The OS retains secret storage, memory, network authority and
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

The attached App payload is staged with the other Apps. Extension deployment
remains an explicit OS `tools/install-browser-agent.sh` operation: it reads
both extension and Native Host from the OS's immutable App source pin, retains
the existing installed paths and configures the chosen extension ID.
This move does not introduce automatic extension installation or APT updates.
`clawd` still owns capabilities, origin injection and privileged socket access.
