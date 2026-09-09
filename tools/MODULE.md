# App Build Tools

`platform_dependency.py` fetches only the SDK/runtime and shared App/gateway libraries selected by
the immutable platform lock. `test.py` runs a product's existing Python/Node
contracts with those libraries. `stage.py` assembles declared App assets for
the OS package builder without installing them on the host.

Native builds remain owned by each product. These scripts must not download
mutable branches at runtime, change App permissions, or overwrite an existing
installed App. Test staging through `tests/test_stage.py`.
CI refreshes the Ubuntu runner's declared distribution sources only, not
unrelated preconfigured third-party repositories. A missing source definition
or failed refresh stops dependency installation; APT signature and hash checks
remain enabled.
`native_build.py` supports libraries and standalone binaries without changing
their upstream workspaces. `stage_native.py` copies declared native assets
from the same product (including Launcher's compiled-in shared Python backend).
Native dependency allowlisting includes the shared toolkit, launcher backend
and Rust SDK/runtime, never core authority or another App implementation.
Nested App layout is preserved and checked against the manifest identity.
Products are discovered from `products/*/package.json`; capability clients from
`capabilities/*/package.json` must declare `kind: "shared-capability-client"`.
Source kind is explicit and duplicate names across roots are rejected. Existing
product/native commands remain product-only; `test.py --capability <name>` and
`stage.py <name> --kind capability` select capability groups. Mixed tests use
`python3 tools/test.py files --capability document-engine`. The test runner selects
each declared App's unit module plus explicit product tests and shared build
contracts; multiple requested products run in one pytest invocation.
`python_library` names a source-owned package under `python/` and its consuming
installed IDs. `python_dependencies` references that export by kind, source
name, library name and consuming IDs, never by an arbitrary path or App call.
Tests add only declared library import roots alongside the pinned OS libraries.
Staging installs those same exports even without their owner's Apps. Co-staging
checks an existing library's complete payload/modes/symlinks and refuses a
conflicting tree instead of merging or overwriting it.
`tests/test_platform_dependency.py` covers immutable pins, sparse library-only
checkout and refusal of modified caches or product-source dependencies.
Binary products may declare `native_examples` for fixture-only executables;
`native_build.py <product> build` builds them separately with the same lock.
Capture declares its `native_process_test` beside these inputs; CI runs that
script against the built binary, original installer and an isolated fake portal.
Media Player uses the same runner with its original standalone renderer graph,
installed resource checks, isolated MCP and a private MPRIS fixture built from
the actual native backend. Fixtures never connect to the user's desktop bus.
Notifications retains its original standalone graph and separately tests/builds
the daemon, configuration and util crates. `native_libraries` explicitly exports
product-owned crates by component-relative path and Cargo identity; staging and
development preparation refuse path escapes or identity mismatches before
copying. OS consumers link the same immutable staged libraries, not App handlers.
Its process fixture covers installed no-bus MCP and typed canned wire responses;
the OS owns real authority/SQLite/delivery/presentation integration tests.
