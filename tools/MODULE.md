# App Build Tools

`platform_dependency.py` fetches only the SDK/runtime directories selected by
the immutable platform lock. `test.py` runs a product's existing Python/Node
contracts with those libraries. `stage.py` assembles product-owned assets for
the OS package builder without installing them on the host.

Native builds remain owned by each product. These scripts must not download
mutable branches at runtime, change App permissions, or overwrite an existing
installed App. Test staging through `tests/test_stage.py`.
