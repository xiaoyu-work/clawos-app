# Claw OS Applications

This repository owns application products, not the operating system.
Read `ARCHITECTURE.md` and the product's `MODULE.md` before changing its boundary.

- Keep each product's UI, business implementation, MCP, manifests and tests
  together under `products/<product>/`.
- Apps never invoke other Apps. The system Agent orchestrates cross-product
  work. Use the versioned SDK/runtime for controlled OS and AI access.
- Keep authority, credentials, consent, audit, App Host and system services in
  `xiaoyu-work/claw-os`. Do not copy their implementations here.
- `platform.lock.json` pins development SDK/runtime and shared App libraries. Fetch them
  through `tools/platform_dependency.py`; never import from a sibling OS checkout.
- Preserve upstream licenses, source pins, executable modes and symlinks.
  Build native products on Linux/WSL's Linux filesystem.
- Keep installed identities and permissions unchanged during repository moves.
  Product identity/data migrations are separate, explicit changes.
- Stage explicit paths and preserve unrelated work. Publish each completed App
  migration with its matching OS consumption/removal commit.
- Use existing pytest, Node and upstream native test runners. Do not run the
  entire vendored source tree as a generic Python test suite.
- Declare product Apps and extra tests in `package.json`; add each new product
  to the CI matrix. The test runner accepts one or more product names.

```bash
python3 tools/test.py mail
python3 tools/test.py mail calendar
python3 tools/stage.py mail --root build/stage
```

These tests do not replace the native product's build or UI acceptance.
