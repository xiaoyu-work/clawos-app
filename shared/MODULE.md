# Shared App Client Libraries

This directory owns common App client support, not OS providers or another
App's entrypoint. The first-party sources retain the root [license](../LICENSE).
The Python helpers originate from `claw-os/apps`. Removing the OS copy and transferring
installed file ownership are coordinated with the consumer/package cutover,
not an App-data migration.

| Source | Import contract |
| --- | --- |
| `python/_shared/` | `_shared.atomic`, `.credentials`, `.env_scrub`, `.paths`, `.safe_http` |
| `python/gateway/_shared/` | `gateway._shared` argument, transport, memory, inbound and subprocess helpers |
| `python/canonical_argv.py` | `canonical_argv` parsing and normalization |
| `rust/gui-argv/` | Private std-only `claw-app-gui-argv` compile-time dependency for native CLI adaptation |
| `../tests/shared/` | Helper behavior, staging/import isolation and App transport contracts |
| `../tests/shared/vectors/` | URL/IDNA/effective-port regression vectors; never runtime payload |

## Native CLI Adapter

`claw-app-gui-argv::normalize` accepts explicit OS-string argv, a GUI-mode bool
and a selector. It removes only an exact, nonempty selector at argv index 1
when GUI mode is selected. It preserves argv0, all other bytes/order, option
values, repeated selectors and `--`; the original product parser retains its
grammar and errors. Direct CLI input is unchanged. The adapter neither reads
nor changes process environment, opens resources, selects a transport nor
confers authority.

Native callers observe GUI mode through the existing SDK 1.0.0
`gui::is_gui_launch()` and pass the Host-forwarded argv directly. They do not
reconstruct it from `COS_ARGS_JSON` or treat the mode marker as authentication.
Notifications has no argv consumer and needs no unused adapter dependency.
The eight consumers compile this App-owned crate into their own binaries;
there is no shared native runtime package, new support ABI or SDK pin.
`tools/native_build.py` resolves its checked-in relative Cargo path for flat
and nested prepared workspaces. Native payload preparation preserves the root
Apache-2.0 license under `licenses/claw-app-gui-argv/LICENSE` in each consuming
App, alongside all original native licenses.

Run the isolated pure parser tests from the repository root on Linux/WSL:

```sh
cargo test --locked --manifest-path shared/rust/gui-argv/Cargo.toml \
  --target-dir build/gui-argv-target
```

Product tests exercise their actual parsers separately; see
[native argv contracts](../docs/native-payloads.md#native-argv-adaptation).

## Python Runtime Libraries

`_shared.atomic.atomic_write_bytes` and `atomic_write_json` accept the additive
`strict=True` option used by Files' private plan records. Strict writes stage
exclusively without following a leaf symlink, require file and directory
fsyncs, and surface every durability failure; an error after replacement may
be indeterminate. Existing best-effort replacement defaults and
`atomic_create_bytes`'s no-replace semantics are unchanged. App-owned helper
regressions live in `tests/shared/test_atomic.py`; no OS provider is copied.

Development puts `shared/python` on the same explicit Python path as the
immutable OS SDK/runtime. Installed Python and native embedded clients use
`/usr/lib/cos/python`. Imports do not search an App parent directory or a sibling
OS checkout. The regular `gateway` package exposes its library namespace without
merging other gateway App directories into it.

## Staging and Ownership

`tools/stage.py` exports `stage_shared(destination)`, returning
`destination/usr/lib/cos/python`. Its CLI is:

```bash
python3 tools/stage.py --shared --root build/support-stage
```

It owns exactly `_shared/`, `gateway/` and `canonical_argv.py` in that root.
These belong to the App-owned common runtime dependency, not OS packages or
individual product packages. `stage(product, ...)` remains separate and stages
only that source's Apps and declared product-specific Python exports.

Staging preflights every common library before writing. Missing libraries,
destination symlinks and differences in bytes, modes, symlink targets or tree
membership fail explicitly. Identical co-staging reuses the existing tree
without rewriting it. Source tests, fixture directories, conftests, pytest
caches and bytecode are excluded; an unexpected test or bytecode file in an
existing owned destination is a conflict, not an ignored payload.

## Authority and Dependencies

The OS retains SDK/runtime implementation ownership, capability enforcement,
credential storage, AI consent/budgets/providers, brokered egress, memory and
audit. App-facing contracts are versioned interfaces, not privileges reserved
for a bundled, native or first-party App. Their consumers must use the same
authenticated manifest/Host/session, capability and sandbox contract regardless
of App language or origin. Identity binds ownership, sessions and audit; a
business name is not an authorization grant.

The common support dependency exposes ABI v1 separately from the OS's versioned
App runtime interface. Package authenticity, an import path, a signed artifact
or the delivery format grants no runtime permissions. Helpers must preserve
provider denials and existing authorization checks; they do not install grants
or execute App-supplied hooks as privileged integration.
Existing grants, validation order, per-redirect checks and result shapes are
unchanged. Apps never invoke one another.

This is the interface contract, not a claim that every OS integration already
satisfies it. Generic Host admission and App-side selector adaptation do not
establish GUI authorization, resource admission, auxiliary entry routing or
Settings policy integration. Preserve the checked-in publication gate and
existing protections until the corresponding OS-owned checks are verified;
see [the remaining native boundaries](../docs/native-payloads.md#deliberately-gated-surfaces).

`_shared.safe_http` requires the distribution's `idna >= 3.3, < 4` library.
The common runtime package must declare that dependency; missing or unsupported
IDNA remains an explicit error. No helper tests or URL vectors enter that
package.

From the repository root on Linux/WSL:

```bash
python3 tools/test.py --shared
python3 tools/test.py mail files terminal --capability document-engine storage-sdk http
```

Tests use synthetic state and local policy/CONNECT wire fixtures, never live AI
or network services. Public MCP fixtures compose product staging, common App
staging and the declared SDK/runtime imports. Native process fixtures use the
same installed root; these tests do not establish native UI or image acceptance.
Artifact/staging and direct protocol fixtures also do not prove unified Host
admission for existing special launch paths.
