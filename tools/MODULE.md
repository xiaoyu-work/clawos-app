# App Build Tools

`platform_dependency.py` fetches only the SDK/runtime and shared App/gateway libraries selected by
the immutable platform lock. `test.py` runs a product's existing Python/Node
contracts with those libraries. `stage.py` assembles product-owned assets for
the OS package builder without installing them on the host.

Native builds remain owned by each product. These scripts must not download
mutable branches at runtime, change App permissions, or overwrite an existing
installed App. Test staging through `tests/test_stage.py`.
`native_build.py` supports libraries and standalone binaries without changing
their upstream workspaces. `stage_native.py` copies declared native assets
from the same product (including Launcher's compiled-in shared Python backend).
Native dependency allowlisting includes the shared toolkit, launcher backend
and Rust SDK/runtime, never core authority or another App implementation.
Nested App layout is preserved and checked against the manifest identity.
Products are discovered from `products/*/package.json`. The test runner selects
each declared App's unit module plus explicit product tests and shared build
contracts; multiple requested products run in one pytest invocation.
`tests/test_platform_dependency.py` covers immutable pins, sparse library-only
checkout and refusal of modified caches or product-source dependencies.
Binary products may declare `native_examples` for fixture-only executables;
`native_build.py <product> build` builds them separately with the same lock.
Capture declares its `native_process_test` beside these inputs; CI runs that
script against the built binary, original installer and an isolated fake portal.
