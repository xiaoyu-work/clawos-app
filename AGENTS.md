# Claw OS Applications

This repository owns application products and explicitly declared shared
capability clients, not the operating system. Read `ARCHITECTURE.md` and the
source group's `MODULE.md` before changing its boundary.

- Keep each product's UI, business implementation, MCP, manifests and tests
  together under `products/<product>/`.
- Keep shared-capability facades under `capabilities/<group>/`, with
  `kind: "shared-capability-client"` in `package.json`. They are not business
  products, new installed identities, or privileged SDK/provider implementations.
- Apps never invoke other Apps. The system Agent orchestrates cross-product
  work. Use the versioned SDK/runtime for controlled OS and AI access.
- Every App uses one authenticated manifest/Host/capability/sandbox model.
  Origin, language, UI and delivery format never confer runtime privilege.
  Identity binds authenticated ownership/session/audit, not business-name
  entitlements. Preserve existing protections until generic replacements and
  regressions are verified; unresolved special integration blocks publication.
- Keep authority, credentials, consent, audit, App Host and system services in
  `xiaoyu-work/claw-os`. Do not copy their implementations here.
- `platform.lock.json` pins a published SDK/runtime/toolkit artifact by version,
  HTTPS URL, SHA-256 and runtime ABI. Fetch it through
  `tools/platform_dependency.py`; never import from a sibling OS checkout.
  Common App Python libraries belong to local `shared/python`, not the OS artifact.
  The compile-time native argv adapter belongs to `shared/rust/gui-argv`; it
  selects parsing behavior only and is not an SDK or runtime authority interface.
  Native products use `prepare_native()` for allowlisted shared toolkit,
  launcher backend and SDK/runtime libraries only; run
  `python3 tools/native_build.py <product> test` for actual native coverage.
- Preserve upstream licenses, source pins, executable modes and symlinks.
  Build native products on Linux/WSL's Linux filesystem.
- Keep installed identities and permissions unchanged during repository moves.
  Product identity/data migrations are separate, explicit changes.
- Stage explicit paths and preserve unrelated work. Publish each completed App
  migration with its matching OS consumption/removal commit.
- Use existing pytest, Node and upstream native test runners. Do not run the
  entire vendored source tree as a generic Python test suite.
- Declare product Apps and extra tests in `package.json`; add each new product
  to the product CI matrix. Shared capability groups use the separate capability
  matrix and explicit `--capability` test / `--kind capability` stage selection.
  Apps without the default `test_main.py` must explicitly declare an App-local
  test file (for example KV's `apps/kv/test_server.py`). Do not invent a
  production `main.py` or empty test just to satisfy a filename convention.
- Declare shared Python dependencies by source kind, source name, exported
  library name and consuming App IDs. Tests and staging resolve the same export;
  do not add sibling-source imports or copy another parser into an App.
- Declare extra package payloads with product-owned `installed_assets` and
  consuming App IDs. Canonical staging invokes `tools/package_assets.py` once;
  release and fixture builders must not repeat it. Common support remains
  separately staged and separately owned.
- Native App payload/launcher work starts at `tools/native_payload.py`, the
  product's `native_payload` declaration, and `docs/native-payloads.md`.
  Source staging is not a compiled App. Preserve real ELF/resource/license
  bytes, use the existing signer and common Host, and keep unsupported
  resource/argument/authority integration explicitly gated.

```bash
python3 tools/test.py mail
python3 tools/test.py mail calendar
python3 tools/stage.py mail --root build/stage
python3 tools/test.py files --capability document-engine
python3 tools/stage.py document-engine --kind capability --root build/doc-stage
```

These tests do not replace the native product's build or UI acceptance.

All 75 original App identities are source-owned here (24 business products,
four capability groups; 63 Agent and 12 desktop identities). Keep source
completion separate from pending backend/state/identity consolidation or new
UI work. AI Helpers owns only the `summarize` client; other products use SDK AI
directly. Its tests must use isolated synthetic public AI/policy/memory wire
fixtures, never paid/live models or another product's consent/budget.

Independent release work starts at [`packaging/MODULE.md`](packaging/MODULE.md)
and [`docs/releases.md`](docs/releases.md). `tools/release.py plan --select ...`
defines the selected package/architecture matrix; release workflows build real
Debian payloads and publish the separate signed App APT channel, never an OS
checkout/build. Preserve one dpkg owner per shared library, the bounded OS
ownership transfer, immutable versions and authenticated metadata freshness.
