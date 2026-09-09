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
- Keep authority, credentials, consent, audit, App Host and system services in
  `xiaoyu-work/claw-os`. Do not copy their implementations here.
- `platform.lock.json` pins development SDK/runtime and shared App libraries. Fetch them
  through `tools/platform_dependency.py`; never import from a sibling OS checkout.
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

```bash
python3 tools/test.py mail
python3 tools/test.py mail calendar
python3 tools/stage.py mail --root build/stage
python3 tools/test.py files --capability document-engine
python3 tools/stage.py document-engine --kind capability --root build/doc-stage
```

These tests do not replace the native product's build or UI acceptance.
