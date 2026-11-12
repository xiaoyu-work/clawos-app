# Store Product

Own the `pkg` App's thirteen existing CLI operations and matching MCP adapter,
and the complete native `cosmic-store` fork, including Flatpak/PackageKit UI,
translations, assets, original Cargo graph and `flathub-stats` workspace member.

| Path | Responsibility |
| --- | --- |
| `apps/pkg/app.json` | CLI/MCP arguments and existing package/observation capabilities |
| `apps/pkg/main.py` | Controlled OS catalog/details/inventory reads, legacy availability preflight and `cos __package` mutation requests |
| `apps/pkg/server.py` | Runtime adapter from manifest operations to SDK MCP |
| `apps/pkg/test_main.py` | Catalog client validation, scoped broker requests and all MCP operation routes |
| `package.json` | Product-owned staging and test inputs |
| `apps/cosmic-store/app.json` | Unchanged four-tool native descriptor and independent grants |
| `native/cosmic-store/src/mcp.rs` | Three catalog queries and fixed Store activation |
| `native/cosmic-store/src/argparse.rs`, `native/cosmic-store/test/unit/argparse.rs` | Native search/helper arguments, bounded Host GUI selector adaptation and parser regressions |
| `native/cosmic-store/src/product.rs`, `product_bridge.py` | Controlled OS catalog reads; embedded human filesystem/snapshot and fixed desktop adapters |
| `native/cosmic-store/src/package.rs`, `backend/packagekit.rs` | Exact Debian intent/correlation, retained Root handoff, status and read-only recovery; PackageKit queries only |
| `native/test_process.py` | Real binary/resource installation and authenticated synthetic stdio fixture |

Preserve the installed `pkg` identity and existing permissions. The OS package
provider now accepts any client with the existing Critical `sys.package` scope
and matching authenticated owner/session; it does not require a `pkg` name.
It still serializes transactions and records mutation/rollback state. Package
effects are system-wide, and this grants neither native Store nor any other
App new default authority. No installed package database, apt configuration or
OS provider code moves into this repository. Product code never invokes another
App, and the GUI must not gain authority by forwarding through `pkg`.

Payload mutations now require the retained Root handoff contract. `accepted`
means only that Root saved the request, not that any package was installed,
removed or restored. Root may retire affected Apps, including this caller.
`need` submits its missing packages together (at most 128) before returning a
receipt; it never waits for its own retirement or reports pending packages as
installed. Root derives a payload/dependency impact closure rather than stopping
every installed App by default. If helper, trigger or shared-runtime effects
cannot be bounded, the existing protected OS review channel must separately
confirm the all-App stop for the exact plan and impact before any such stop.
Neither Critical package permission, an App-install review nor a client flag
supplies that confirmation. The owner uses `cos package-transactions [request-id]` or
`--invocation <id>` outside the affected App to inspect completion. `--recover`
performs read-only outcome reconciliation and never replays APT. App deliveries
still need separate protected per-App confirmation; Critical package permission
does not supply it. Query/search and index/hold metadata operations retain
their existing behavior. Older clients/brokers must refuse the handoff marker
or typed correlation field, rather than fall back to an uncoordinated installer.

```bash
python3 tools/test.py store
python3 tools/stage.py store --root build/store-stage
python3 tools/native_build.py store test
python3 tools/native_build.py store build
python3 products/store/native/test_process.py
```

Tests mock package queries and mutations; they do not install or remove software.
The three `pkg` catalog operations use the same OS reader through the published
Python SDK kernel transport. Their existing permission checks and result fields
remain; the App no longer parses or directly opens APT/dpkg catalog state.
The shared Web inventory copy describes the new installed-state snapshot rather
than treating dpkg selections as installation proof. Availability and `need`
preflight still have their separate legacy query integration gate.
Native MCP uses the public SDK's generic call primitive for the closed
`cos __package_query` search/details/installed interface. Root independently
requires `sys.observe:packages` for search/list and the exact named observation
scope for details. The App receives metadata, not raw system D-Bus or APT/dpkg
state mounts; package mutation authority does not substitute for read access.
An older runtime refuses the interface without a local-query fallback.
The installed-process fixture supplies a synthetic OS reader and no local
apt/dpkg executable. The worker's authenticated session stays intact; call
metadata does not grant pkg authority.
The remaining human filesystem adapter still embeds the product library and
uses isolated system Python with installed OS SDK/runtime and App-owned common
support from `/usr/lib/cos/python`; it never invokes another App entrypoint.
Human-only Flatpak data cleanup checks `fs.delete` and snapshots before removal;
ref-file reads check `fs.read`. Both adapters reject MCP use. New Window and
`store.open` use a fixed broker target under `proc.spawn:cosmic-store`.
Native Debian install/remove/purge/update actions now submit one exact single
or bounded batch intent to the existing Root package controller. The GUI has
an explicit empty mandatory needs list and starts without Critical package
authority. Its optional declaration describes the package feature, not consent.
Root must bind this exact signed GUI, owner/session, action, package set and
invocation to ordinary protected Critical `sys.package` reviews. Only Root
redeems the complete decision set and retains its real expiry/revocation bounds
for one unindexed package use; neither an App dialog nor the review-ready
status authorizes effects, and the GUI's startup grant is never widened.
The package-only private GUI transport/shared wiring needs coordinated OS
integration; older CLIs/daemons fail closed without a provider fallback.

The client saves intent/correlation in its own authenticated `COS_DATA_DIR`
before dispatch, and reopens cached intents as **unconfirmed**, never as cached
success. A resumed intent can request OS review only, without spending decisions
or replaying effects. Root terminal reconciliation may trim this local pending
bookkeeping, but the OS retains the actual transaction evidence.
Accepted requests appear as handed off, not Installed/Removed; Root
may stop Store itself. Check OS status and read-only recovery are explicit,
bounded requests, not a GUI-blocked wait or an automatic mutation retry.
Recovery itself is retained by Root before returning so it cannot wait on
publication while the controller waits for this GUI provider to retire.
Only a matching authenticated Root `applied` record with confirmed completion
can report applied; even the codec helper cannot turn acceptance into success.
Unknown `/usr` readers still require the separate protected global-impact
review in top-level OS Approvals (`cos agent serve --open`), and App deliveries
still need independent per-App confirmation. The active `clawd` package remains
refused by the same Root controller.

PackageKit remains a catalog/query backend only: no payload mutator,
interactive polkit transaction or privileged cache refresh remains in Store.
Local `.deb` files are explicitly unsupported by the authenticated APT-channel
transport; metadata is not authority to install arbitrary archives. Flatpak
catalog/installed/source presentation remains, but refs, updates, removals,
rebases and repository changes fail with `OS_PACKAGE_PROVIDER_UNSUPPORTED`.
There is currently no typed retained Root Flatpak provider; its future contract
must bind owner/session, exact user/system installation, remote/ref/commit and
dependencies, checked runtime/GUI retirement, unknown helper/shared effects,
protected consent, durable outcome/inverse and read-only recovery. Flatpak IDs
are never passed to Debian, and no App-owned root D-Bus/helper exception exists.
Catalog refresh rereads existing metadata rather than activating privileged
PackageKit/Flatpak refresh helpers.

UI catalog/backend consolidation, installed-data migration, genuine GUI
self-handoff against private APT, full-image integration and interactive/visual
acceptance remain separate gates. This source does not complete native Store
acceptance or approve publication, an SDK freeze or adoption of a new App pin.

The native payload binds GUI and MCP to the real `bin/cosmic-store`, preserving
resources and licenses. Its compatibility command enters the existing common
Host rather than invoking the relocated ELF directly. The App-owned
`claw-app-gui-argv` library removes one exact argv[1] `--gui` only in SDK GUI mode,
after the existing MCP dispatch. Search/URI/codec strings and helper option
values retain their original boundaries; `-- --gui` remains a positional value.
Help still exits successfully, and the unconfigured `--version` still errors.
This parsing adaptation does not enable resource/provider integration. See
[native payloads](../../docs/native-payloads.md).
