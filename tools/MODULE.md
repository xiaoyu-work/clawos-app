# App Build Tools

`platform_dependency.py` fetches only the SDK/runtime and shared App/gateway libraries selected by
the immutable platform lock. `test.py` runs a product's existing Python/Node
contracts with those libraries. `stage.py` assembles product-owned assets for
the OS package builder without installing them on the host.

Native builds remain owned by each product. These scripts must not download
mutable branches at runtime, change App permissions, or overwrite an existing
installed App. Test staging through `tests/test_stage.py`.
Nested App layout is preserved and checked against the manifest identity.
`tests/test_platform_dependency.py` covers immutable pins, sparse library-only
checkout and refusal of modified caches or product-source dependencies.
