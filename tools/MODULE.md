# App Build Tools

`platform_dependency.py` fetches only the versioned public platform artifact
selected by `platform.lock.json`. `platform_archive.py` verifies its public
`claw.app-platform/v1` inventory and extracts it with `tarfile`'s data filter.
No Git fetching, OS source checkout, sibling lookup or unverified cache fallback
remains. Its Python paths include the named SDK/runtime exports and local
App-owned `shared/python`, never OS `apps/`.
`manifest_schema_path()` resolves the public SDK manifest contract, not private
core source. `test.py` runs declared Python/Node contracts with these imports.
`stage.py` assembles declared App assets without installing them on the host.
`package_assets.py` stages `installed_assets` declared by a product's
`package.json`: each entry names a source file/directory, a root-relative
installed destination under `usr/`, and the owning declared App IDs.
Canonical `stage(product)` invokes this helper for declared installed assets;
release/fixture builders call the canonical stager without a duplicate asset
pass. Its standalone CLI is for asset-only staging into a fresh root:
`python3 tools/package_assets.py browser --root build/browser-assets`.
Only selected owners (`--apps`) receive the assets. All declarations/targets are checked
before asset writes; overlaps, unowned sources, escaping links and conflicting
installed paths fail. The common payload filter excludes tests and bytecode,
while source executable modes are preserved. Browser uses this for its complete
WebExtension and fixed canonical-host launcher; release and fixture assembly
use the same contract rather than copying another native host implementation.

The lock has exactly `version` (release SemVer), `url` (HTTPS),
`sha256` (64 hexadecimal characters), and `runtime_abi` (currently integer `1`).
It may additionally declare `schema: "claw.app-platform/v1"`. Old repository,
revision and source-selection fields are errors. Publication must supply the
real release URL and digest; a probe fixture or placeholder is not a release pin.
`validate_lock(lock)` exposes that same pure validation to release callers;
`read_lock()` applies it to the bounded repository lock file.

Downloads and every redirect must remain HTTPS. Private project-local temporary
files are bounded to 128 MiB compressed, 512 MiB expanded, 64 MiB per file,
8 MiB metadata and 50,000 inventory nodes. SHA-256 verification precedes tar
inspection; inventory checks precede standard filtered extraction. The complete
candidate is validated before atomic cache publication.

Caches live under `build/platform-artifacts/<sha256>/`, containing only a retained
`archive.tar.gz` and `payload/`. Every use re-verifies the archive into a private
snapshot and derives expectations from its `platform.json`, not mutable
extracted metadata. Missing/extra files, bytes, modes, unsupported nodes and
changed symlinks fail without repair or redownload. Exactly required implicit
ancestor directories are allowed, including `desktop/`; unrelated entries are
not. The raw archive layout preserves relative Cargo dependencies.

`prepare_exports()` returns named verified paths; `download=False` is cache-only,
not a verification bypass. `prepare()` retains the SDK Python root, runtime
Python root and local App support root in that order. `prepare_native()` returns
the `ui-toolkit` export: its parent is the artifact's `desktop/` and its
grandparent is the payload root. Native builds use a mutable prepared App
workspace/lock and an external Cargo target directory. Direct SDK tests must
likewise stage their workspace/lock from the verified artifact into a separate
test-owned build area, not run Cargo on the verified library manifest. Test
scratch belongs beneath the external test executable/target, not the artifact's
`CARGO_MANIFEST_DIR`. `test.py` disables bytecode so imports do not mutate verified SDK
sources. Staged Python/native test fixtures select named exports cache-only;
Mail's source-checkout native host also verifies the cache without downloading.

These are versioned App interface exports, not an OS-private entitlement for
bundled clients. `prepare_exports()` needs no App source tree, identity or origin
classification. `prepare()` additionally composes this repository's local App
helpers; that build convenience does not grant authority. `prepare_native()` is
a toolkit-selection convenience, not a privileged integration category.
Every App still requires the same authenticated manifest/Host/session,
capability and sandbox contract. A signed archive or Debian package is not a
permission grant or authorization to run an App-supplied root hook.

`stage_shared(destination)` separately stages the common App support dependency
to `destination/usr/lib/cos/python`; `--shared --root <destination>` is its CLI.
The exact owned entries are `_shared/`, `gateway/` and `canonical_argv.py`.
Individual product/capability staging does not duplicate them. Both installed
Python Apps and native embedded clients use this root, alongside OS SDK/runtime.
Missing or conflicting payloads fail before common-library writes; identical
bytes, modes and symlink trees are reused. Tests and bytecode are not payload.
See [`../shared/MODULE.md`](../shared/MODULE.md) for ownership and dependencies.

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
`test.py --shared` selects helper, staging and static manifest contracts without
collecting vendored product trees. Helper tests/vectors live under `tests/shared`;
public MCP fixtures explicitly compose common and product payloads.
`python_library` names a source-owned package under `python/` and its consuming
installed IDs. `python_dependencies` references that export by kind, source
name, library name and consuming IDs, never by an arbitrary path or App call.
Tests add only declared library import roots alongside common App support and
the pinned OS libraries.
Staging installs those same exports even without their owner's Apps. Co-staging
checks an existing library's complete payload/modes/symlinks and refuses a
conflicting tree instead of merging or overwriting it.
`tests/test_platform_dependency.py` covers synthetic HTTPS downloads, exact
pins, bounded/filtered tar extraction, malicious inventories and links, atomic
publication, cache tampering and isolated native-host bootstrap. An explicit
local OS-built probe can test real SDK imports without a production override:

```bash
PYTHONPATH=tests:shared/python python3 -m pytest -q --import-mode=importlib \
  tests/test_platform_dependency.py \
  --platform-artifact-fixture=/path/to/claw-os-app-platform-1.0.0.tar.gz
```

The optional test fixture path is test-only; production always uses the lock's
HTTPS URL and digest. These checks do not establish a native UI build or release
acceptance before the final platform artifact is published.
They also do not establish origin-independent OS Host admission: existing
business-name executable bindings and native-host exemptions require generic
replacements with equivalent provenance, ownership and sandbox protections.
Earlier Notifications config/util candidates were not generic runtime services.
Native-owner source checks now report OS consumers use the public SDK
presentation protocol without App libraries. Final SDK publication and runtime
admission remain separate; delivery checks do not prove unified integration.
Binary products may declare `native_examples` for fixture-only executables;
`native_build.py <product> build` builds them separately with the same lock.
Capture declares its `native_process_test` beside these inputs; CI runs that
script against the built binary, original installer and an isolated fake portal.
Media Player uses the same runner with its original standalone renderer graph,
installed resource checks, isolated MCP and a private MPRIS fixture built from
the actual native backend. Fixtures never connect to the user's desktop bus.
Notifications retains its standalone graph and private daemon/config/util
packages, but no longer exports config/util libraries. OS consumers use
`claw-os-sdk/rust/notification-presentation` from the normal SDK artifact.
Other declared data-only library fixtures retain path/identity checks; retired
Notifications exports cannot re-enter release or development artifacts.
Notifications process fixtures cover installed isolated MCP and actual private-FD
old/new presentation handoff; real authority/SQLite/delivery ownership stays OS-side.
