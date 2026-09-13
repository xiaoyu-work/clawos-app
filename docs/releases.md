# Independent App releases

App delivery is subordinate to one verified App install/review contract.
This repository owns product payloads, independent versions, build/test jobs,
authenticated App snapshots and release catalogs. The tested Debian/APT builders
remain explicit compatibility delivery, not installation approval or authority.
The OS owns installation, protected human review, capability enforcement,
App provenance, security-floor gates and user state. There is no additional
privileged updater, runtime source checkout, model-controlled signing key or
trust-root override.

## Platform publication status

App development platform `1.0.0` and `1.1.0` releases, tags and uploaded Actions
artifacts have been withdrawn at the owner's request. The OS platform source
version is back to **unpublished `0.1.0`**; there is no replacement
`app-platform-v0.1.0` release.

The uncommitted `1.1.0` adoption has been reverted. `platform.lock.json` retains
its historical `1.0.0` URL and digest, so a fresh environment cannot download
that dependency. Existing local caches and validation artifacts are not a
current publication. Do not fabricate a `0.1.0` URL/digest, substitute a sibling
OS checkout or republish an artifact to bypass this blocked dependency.

Source development can instead explicitly supply a local archive with its
expected version and SHA-256; see
[local platform development](../tools/MODULE.md#local-platform-development).
This verifies the same public artifact format in a separate cache. It does not
make the default CI dependency available, change `platform.lock.json`, authorize
release/install payload staging or select another source at runtime.

Any future release, release tag, version bump or dependency-pin adoption needs
explicit owner approval. Source development, successful validation and requests
to commit or push do not authorize publication.

## One App integration contract: pending

The design is accepted; this status tracks implementation/integration acceptance,
not an unresolved choice of App model.

Every App must use the same authenticated manifest, App Host, capability,
resource-owner and sandbox contract. Language, UI, package origin and the
`agent`/`desktop` payload partition are not authority categories. Signatures
authenticate package bytes; installed ownership and App identity bind resources,
sessions and audit records, not implicit grants or business-name privileges.
Versioned SDK/runtime/service interfaces must be usable by any appropriately
authorized App, not only bundled clients.

Before installation the OS must disclose authenticated requested permissions,
scopes and purposes and obtain human confirmation. Installation is not a blanket
capability or AI grant. Permission-relevant updates require disclosure/review;
an App or Agent cannot acknowledge on the user's behalf. A review
`contract_digest` is comparison data, not an approval token. Multiple Apps may
implement the same function; default selection does not confer exclusivity.
These are plugin-style extension contracts, not a new package kind or plugin flag.

Terminal and desktop review must be consistent OS-owned presentation, independent
of an App's UI. App purposes come from existing localized `needs[].why` fields.
The OS owns per-App allow-within-selected-scope, ask and deny decisions and their
enforcement across GUI, MCP and background execution. No real revocation means
no enabled UI toggle. This repository does not add a purpose/plugin flag,
decision store, review presenter, grant or revocation implementation.

**New publication is blocked** by
`packaging/release.json`'s `integration_contract` review state. The publisher
refuses before GitHub or signing until coordinated generic contracts and their
regressions justify `verified-origin-neutral-app-host`. There is no environment
override. This is a release-readiness check, not a runtime trust switch.
Authenticated refresh of existing signed APT metadata remains available.
Local packages and compatibility archives are validation candidates, not proof
that the runtime integration model is unified.

The following dependencies were reported at the parent-verified checkpoint and
require coordinated close-out. This producer does not establish their
replacement or remove/weaken their protections:

| Existing surface | Outstanding contract |
| --- | --- |
| OS `core/src/worker/trusted_desktop.rs::verified_entrypoint` | Generic signed package-relative entry admission has replaced the fixed launch table. The nine native producer manifests/payload plans now use it; this does not establish runtime resource or provider integration. |
| Mail opaque stdio integration | The `TrustedNativeHost` exemption is removed. Mail still requires its ordinary declared stdin operation and common Host/controller integration; no publisher-created fallback or native-host flag is introduced. |
| Browser Native Messaging launcher/host | The package-owned direct Python launcher and root-peer socket check must be reconciled with generic authenticated App Host/session binding. Packaging preserves those checks; it does not establish an exemption. |
| OS `core/src/clawd/packages.rs` | Fixed `pkg` client gating is replaced by the existing Critical `sys.package` authority, exact requested scope and authenticated owner/session. Each client retains its identity; global actions still require explicit wildcard authority and rollback must match recorded inverse state. Effects remain system-wide. No default App grants, installation-review bypass or publication readiness follows. |
| OS App permission-management service | `system.app-permissions` now accepts independently authorized Apps through the existing High-risk `sys.permissions:manage` capability and authenticated owner, not a fixed Settings identity. It can inspect, request restoration and revoke supported permissions; trusted OS approval, target validation and checked retirement remain mandatory. This does not complete GUI permission acquisition or permit App-owned approval. |
| OS media-player route | Fixed `cosmic-player` caller gating is replaced by the existing exact observation/control capabilities and authenticated owner/session. Each calling App retains its identity and live denial policy. The native playback target, executable/PID/unique-connection checks, bounded helper and dispatch gate remain fixed; this is not arbitrary-player discovery, a default grant or completion of installed-resource/GUI integration. |
| App persistent storage | The OS binds the existing owner/App data partition through exact-App private idmapped views for service Hosts and, after Root registration authorization, task-host ordinary operations. Host/UID replacement does not copy, chown or delete backing files. Calendar's cross-App read service remains incomplete; this does not complete installed-App or GUI resource acceptance. |
| Applet SDK/provider and three human-only GUI launchers | Native follow-up reports inherited arbitrary-App identity policy tests and the generic `AppLaunch.bind -> AppIdentitySession::for_gui -> prepare_app_worker` path, without a new trust tier or MCP allowlist row. These positive checks do not resolve the other Host/executable-binding gaps. |
| Clipboard `copyq.rs` and history-check service | The provider check is permission preflight; App code then executes CopyQ. An App can omit its own preflight, so authoritative resource enforcement must live in the generic OS service/sandbox boundary. Preserve the current check until the backend replacement is verified. The Debian `copyq` dependency is availability only. |
| Native payload/runtime integration | [`native_payload.py`](../tools/native_payload.py) prepares real package-local ELFs and common-Host exports. Native GUI argv, Files' auxiliary applet and installed-resource/provider bindings remain explicitly gated; see [the bounded contract](native-payloads.md). |
| Settings `native/cosmic-settings/justfile` | The installer currently copies `cosmic-settings.rules` and `com.clawos.Settings.Users.policy` into system polkit paths. The rule grants locale/keyboard/modem/hostname actions to active sudo/wheel users. The uniform delivery validator rejects this App-supplied authority configuration; move/generalize authority through the OS contract rather than exempt Settings or silently strip protection. |
| Notifications presentation boundary | OS consumers use `claw-os-sdk/rust/notification-presentation` without App config/util or an interface tree. The historical SDK 1.0.0 release has been withdrawn; see [platform publication status](#platform-publication-status). App config/util remain private; no old archive is restored, and signature/presentation definitions do not establish runtime activation. |

Parent verification confirms `cosmic-applets` Cargo/main/build no longer
references Calendar, Clipboard or Widget Rail. That completed separation is
useful but does not resolve the distinct runtime/authority gaps above.

`release_payload.py` enforces the same delivery rules for every package:
no App-supplied Debian maintainer/configuration/trigger hooks, system-service or
system D-Bus activation, polkit/PAM/udev/sysusers/tmpfiles policy, owner-state or
grant payloads, setuid/setgid bits, file capabilities or access ACLs. It validates
both staging and the actual `.deb` archives before indexing/signing, without
executing package code. Ordinary OS-owned package-manager cache triggers remain
OS behavior; an App cannot supply their implementation. These structural checks
cover declared delivery surfaces, not every possible system loader or resource
ownership graph. They do not establish generic installed-resource ownership or
replace Host authentication and runtime capability/sandbox enforcement.

## Verified App snapshot producer

[`tools/release_snapshots.py`](../tools/release_snapshots.py) packages explicitly
selected, already prepared and signed App directories. Every directory has its
own original `app.json` and existing `claw.provenance/v1` `.provenance.json`,
with package kind `app`. It does not merge identities, rewrite manifest/App
versions, author permission summaries, grant permissions or run App entrypoints.
Product preparation must include the complete App-owned binaries, resources and
licenses before signing; this producer copies the entire tree, without payload
filters, build hooks or installed-system path mappings.

Sign prepared trees with the existing public
[`cos provenance sign` contract](https://github.com/xiaoyu-work/claw-os/blob/main/docs/extension-provenance.md#publisher).
The release producer deliberately does not implement Ed25519 canonicalization,
import OS implementation code, create trust roots, or silently sign unsigned
inputs. The publisher key must be authorized for `package-signing` and kind
`app` through the verifier's ordinary protected trust roots. Development trust
is not a publication substitute. The App APT OpenPGP key authenticates catalogs;
it is **not** an App provenance key merely because it signs Debian delivery.

From this repository root, after setting `COS_BIN` and `COS_BIN_SHA256` from
the verified public CLI artifact, `APP_PUBLISHER_KEY_ID` from the checked-in
App publisher contract, and the two existing App APT signing secrets:

```bash
python3 tools/release_snapshots.py build \
  --app-directory build/prepared/first-app \
  --app-directory build/prepared/second-app \
  --release-version 1.0.0 --architecture all \
  --cos "$COS_BIN" --cos-sha256 "$COS_BIN_SHA256" \
  --publisher-key-id "$APP_PUBLISHER_KEY_ID" \
  --output build/app-snapshots-1.0.0

# Verification requires the public archive key, not private APT signing secrets.
python3 tools/release_snapshots.py verify \
  --cos "$COS_BIN" --cos-sha256 "$COS_BIN_SHA256" \
  --publisher-key-id "$APP_PUBLISHER_KEY_ID" \
  --output build/app-snapshots-1.0.0
```

Inputs/output must be explicit non-overlapping directories under `build/`.
Output must not already exist. Each invocation selects one architecture:
`all`, `amd64`, or `arm64`. An ELF cannot be labeled architecture-independent
or assigned the wrong machine architecture. All declared operation/GUI and
MCP/background execution entries must be signed, package-local regular files,
without product/vendor/language exceptions. Binary entries require executable
mode. The producer follows the public Linux manifest runtime defaults:

| Runtime | Operation/GUI entry | MCP/background entry |
| --- | --- | --- |
| `python` (default) | `main.py` | `server.py` |
| `node` | `main.js` | `server.js` |
| `shell` | `main.sh` | `server.sh` |
| `binary` | `main` | `server` |

Explicit `entry` and `mcp.entry` override those defaults without rewriting
`app.json`. MCP-only Apps do not acquire a fabricated `main.py`; lazy,
always-on and while-app-running services use the same signed-entry rule.
`desktop.exec` remains arguments for the OS-owned `cos app` launcher, not
an independent executable path or a package hook. This entry binding is not
runtime admission or permission enforcement, and it does not authorize direct
GUI/resource registration or rewrite compatibility installers' absolute paths.

Each successful output contains:

| File | Contract |
| --- | --- |
| `claw-app-snapshot-<sha256>.tar.gz` | Deterministic archive rooted directly at `app.json` and `.provenance.json`, preserving complete regular-file bytes, modes and empty directories |
| `catalog.json` | `claw.app-snapshot-catalog/v1`, distribution `release_version`, `runtime_abi: 1`, and one record per selected App identity/architecture |
| `catalog.json.asc` | Detached signature under the checked-in App archive OpenPGP key |
| `SHA256SUMS`, `SHA256SUMS.asc` | Exact catalog/archive checksum set and its detached signature |

Each catalog record contains only `app_id`, `app_version`, `architecture`,
`artifact`, `manifest`, and `provenance`. `artifact` binds its relative
content-addressed filename, size, SHA256 and `application/gzip` media type.
`manifest` binds path `app.json`, its exact raw-byte size and SHA256, not a
reserialized or summarized permission projection. `provenance` binds path
`.provenance.json`, its SHA256, authenticated `content_digest` and publisher
key ID. The original App version is distinct from the distribution version.
SHA256 fields use 64 lowercase hexadecimal characters; provenance content/key
IDs retain the public `sha256:` prefix.
The exact manifest includes operation and MCP scopes, conditions, localized
`needs[].why`, desktop declarations and service lifecycle. Changes to those
bytes change the manifest/artifact binding even if an App version is unchanged;
they do not produce a decision or approval cache. Catalog schemas reject
App-supplied permission summaries/choices, review receipts, `contract_digest`
and first-review claims even when signed by the archive key.

The producer verifies its private App copies through the digest-pinned public
CLI, creates/signs the catalog, then extracts and verifies the actual archives
again before atomically exposing the complete output. The verifier authenticates
catalog/checksum signatures before following artifact names, checks exact
artifact bytes, safely extracts bounded payloads, re-verifies App provenance,
and compares the catalog against the authenticated manifest/envelope. Even a
valid APT signature cannot substitute different App manifest data or authorize
changed App code. App root hooks, special nodes, privilege-bearing/writable
modes, links, case collisions and unsigned extended metadata fail.
Catalog verification first copies its bounded regular files to a private
snapshot, so replacing the input after authentication cannot change the
metadata being consumed. Raw tar headers are bounded before extended-header
parsing: 8 MiB per metadata/header body, 100,000 payload nodes and a 2 GiB
payload/catalog budget. Nested metadata, sparse/link headers, truncation and
unindexed trailing data fail before extraction; ordinary long UTF-8 paths use
the standard PAX/data-filter implementation.
The current public `claw.provenance/v1` signer does not admit symlinks.
Preparation must resolve any required delivery-layout change explicitly; the
producer never silently dereferences, drops or invents a signed link.
There is no `.deb` maintainer-hook execution or post-extraction installer.

**OS consumer contract:** authenticate the catalog and exact artifact, verify
the extracted App with the existing provenance machinery, then request
`cos app install <directory> --review`. Its preflight has `installed: false`
and `permission_review.permissions_granted: false`; permissions/scopes/purposes
come from authenticated manifest bytes, not this catalog. Protected human
confirmation, permission-change review, re-verification and activation remain
OS responsibilities. A signature, catalog selection, default App, printed
review JSON, `--yes` or matching `contract_digest` is never first-review proof
and never grants capabilities. The OS's terminal and desktop presenters use
the same protected controller/policy state for scope-limited allow, ask and
deny; an App UI cannot replace those presenters or acknowledge for its user.
Store/APT/first-use integration must honor that same contract before publication.

**Not yet production inputs:** a versioned public CLI/runtime artifact exposing
`cos provenance sign`, `cos provenance verify` and the reviewed install API;
its verified executable digest; and the checked-in App Ed25519
`package-signing` publisher/trust contract. The development SDK/runtime export
does not currently supply this CLI, and installed `cos` 0.1.0 lacks provenance.
An explicitly supplied local CLI fixture supports signature-format testing,
not a production artifact pin. The implemented package-local entry contract
does not add resource mounts, dependency activation or Browser/Mail registration.
Existing Python operation/GUI wrappers still require `main.py`; that limitation
must neither become a rewritten fallback manifest nor restrict valid MCP-only
or opaque-stdio declared entries.
Existing publication gates remain unchanged, and this producer has no publish,
download, package-install or trust-mutation command.

Focused checks use a supplied public CLI fixture and temporary Bubblewrap
namespaces for real signing/trust/verification, plus the existing isolated GPG
fixture; they never modify host trust or install Apps. Optional native acceptance
also discovers MCP tools from an actual extracted ELF inside a separate empty,
no-network/no-desktop sandbox:

```bash
python3 -m pytest -q tests/release/test_snapshots.py \
  --provenance-cos-fixture="$COS_BIN"
```

Without that explicit fixture, signature integration cases are reported as
skipped, not replaced with fabricated envelopes or unsigned success.

The [native payload preparation contract](native-payloads.md) covers all nine
native MCP products, explicit signer entrypoints, byte/mode/license preservation,
Host-only compatibility launchers and the separate resource/runtime blockers.

## Packages and ownership

[`packaging/release.json`](../packaging/release.json) defines the channel and
compatibility policy. [`tools/release.py`](../tools/release.py) derives the
package catalog from each explicitly kinded `package.json`:

| Package | Contents |
| --- | --- |
| `claw-app-<product>` | The product's headless identities, if any |
| `claw-app-<product>-desktop` | Native graphical identities, binaries and original installed resources |
| `claw-cap-<group>` | Explicit shared-capability client identities |
| `claw-app-support` | App-owned `_shared`, `gateway._shared` and `canonical_argv` under `/usr/lib/cos/python` |
| `claw-apps-agent` | Recommended headless set: 63 identities, their libraries and capability clients |
| `claw-apps-desktop` | Recommended graphical set, including the headless set and twelve native identities |

Native-only products such as Editor and Capture have only a `-desktop` package;
installers should use the package catalog rather than assume a headless alias.
Mail additionally has an architecture-independent `-desktop` asset package.
Its existing XPI installs in Thunderbird's distribution extension
directory and depends on system `thunderbird`. Its native Mozilla fork is **not**
built or claimed as a completed replacement. The existing `claw-mail-ai-host`
authority launcher remains OS-owned, but its special integration is an unresolved
contract above, not an approved privileged App category.

`claw-app-browser` owns all three Browser Apps, the complete declared MV3
extension at `/usr/share/claw/extensions/claw-agent-browser`, and executable
`/usr/lib/cos/claw-browser-host`. The launcher executes `/usr/bin/python3`
with the canonical `/usr/lib/cos/apps/browser-attached/native_host.py`; it never
duplicates that implementation under `/usr/lib/cos/browser-agent`.
Browser's `package.json` declares these `installed_assets`, scoped to
`browser-attached`. Canonical `stage.py` invokes the `package_assets.py` helper
once alongside App/library staging; release assembly does not stage them twice.
Common support remains a separate package. Their version
and ownership therefore change together in one normal Browser APT upgrade,
without installing Chromium or a separate Browser desktop package.
The OS integration command only checks installed files and registers the chosen
extension ID in Chromium Native Messaging/policy configuration. It does not
fetch App source, copy implementations, or overwrite package assets. Browser
profiles, registration, grants and owner data are not package payloads.
An already running browser/extension still needs its ordinary reload/restart;
packages do not terminate user processes or enable a force-install policy.

`claw-apps-agent` has no dependency on the desktop set, native graphical App
packages, Thunderbird or Chromium. On minimal hosts, `--no-install-recommends`
also avoids optional recommendations from the OS runtime package. Mixed products'
desktop subpackages depend on the same product's matching headless version;
unrelated products retain independent versions.

Every installed identity retains its own manifest, entrypoint, grants and
owner-scoped data. A product group is a distribution unit, not a merged identity.
Packages contain no user-data payload or data-migration/deletion maintainer
scripts.

Files alone owns `/usr/lib/cos/python/claw_files`; Document Engine depends on
`claw-app-files` and its exact `claw-app-python-claw-files-v1` library ABI.
Consumers do not duplicate the export, even though standalone development
staging can materialize the dependency. Common support similarly provides
`claw-app-support-v1`. Keep these ABI names while compatible; introducing a
breaking library ABI requires an explicit consumer change, not a silent merge.
Neither ABI is an exact product or OS release-version lock.
Common safe HTTP/IDNA helpers require Debian `python3-idna (>= 3.3)` and
`python3-idna (<< 4)` through `claw-app-support`; consumers do not vendor a
separate IDNA implementation or install it dynamically.

Apps depend on `claw-os-app-runtime-v1`, with additional permission, capture,
media-player and notification service interfaces where required. Native runtime
library dependencies are computed from the actual installed ELF binaries with
`dpkg-shlibdeps`. Python/system package mappings remain explicit in the release
configuration.
These dependencies express public interface availability, never a grant, a
special caller class or a sandbox exemption. Existing names remain for
compatibility while the general service/Host contracts above are resolved.
Calendar, Clipboard and Desktop Widgets' standalone desktop packages additionally
depend on `claw-os-applet-services-v1 (= 1)`. The OS provides the fixed
`/usr/libexec/claw-os-applet-provider --stdio-v1` interface and retains policy
and service implementations; App packages install only their own presentation
binaries/resources. This service ABI is not required by Calendar/Clipboard's
headless package or an OS package-version lock.

Debian trixie does not provide `python3-pptx`. Files therefore owns the explicitly
SHA256/size-pinned pure `python-pptx` wheel, including its upstream MIT license
and distribution metadata, under `/usr/lib/cos/python`. Its available Debian
dependencies (Pillow, lxml, XlsxWriter and typing extensions) and the other
document parser dependencies are Files dependencies. Document Engine reuses
that owner, rather than depending on a nonexistent Debian package or installing
packages with pip on the user's machine. The build cache is rehashed on use;
different bytes and unsafe/architecture-specific wheel paths are refused.

### First ownership transfer

The initial split requires OS packages **at least `1:0.3.0`**, which no longer
own the transferred files and still enforce the OS security floor. App packages
declare bounded `Breaks` and `Replaces` against the former owner
`(<< 1:0.3.0)`. Headless/support payloads and Mail's XPI replace old
`claw-os-agent` ownership; other native payloads replace old
`claw-os-desktop` ownership. These declarations never authorize replacement
of a newer OS package. Calendar, Clipboard and Widget Rail replace the former
Desktop `/usr/bin/claw-applet-*` aliases with their own real executables at the
same paths, together with the original desktop entries/icons. This does not
change their human-only identities or move user data.
Upgrade the OS platform boundary in the same ordinary
APT transaction before installing the split Apps. Do not weaken an OS gate,
force an overwrite or delete owner data to make the transition install.
The OS security epoch and protocol ABI remain **1**; only its package-version
compatibility boundary advances from `1:0.2.0` to `1:0.3.0`. The OS's signed-channel
bootstrap/cutover guard must prove the App channel and required packages are
available before removing old bundled payloads.

## Build and test a selection

Run from this repository's root on Linux, with outputs under `build/`:

```bash
python3 tools/release.py plan --select files,capability:document-engine --version 1.2.3
python3 tools/release.py test --plan build/release-plan.json --architecture all
python3 tools/release.py build --plan build/release-plan.json --architecture all

# Run on the matching native Debian trixie architecture:
python3 tools/release.py test --plan build/release-plan.json --architecture amd64
python3 tools/release.py build --plan build/release-plan.json --architecture amd64

python3 -m pytest -q tests/release --basetemp=build/release-tests
git diff --check
```

Selectors are comma-separated product names, `capability:<group>`, `support`,
`sets`, or the single selector `all`. Versions use
`MAJOR.MINOR.PATCH[~alphaN|~betaN|~rcN][-REVISION]`; epochs, shell expressions,
leading zeroes and arbitrary path/tag syntax are rejected. A release plan binds
the source commit, version, exact package partitions and architecture matrix.
Support and set updates are explicit selections; releasing one App does not
implicitly rebuild/release them or another product.
Complete source/staging fixture archives are opt-in with `plan --fixtures`
(workflow input `fixtures=true`, default false). They never force unrelated
product builds or gate installed-system distribution.

Python packages are built once as `Architecture: all`, with normalized
timestamps, root ownership and deterministic compression. Native jobs run on
native amd64 and arm64 GitHub runners inside Debian trixie containers, use the
configured Rust toolchain and locked dependency graphs, and run actual upstream
builds. The original `just install` recipe installs privately. For the nine
declared `native_payload` products, the stager then places real ELFs inside
their App directories and exports only common-Host compatibility launchers.
`--app-root` prepares an unsigned App directory for the existing signer;
`--install-root` additionally validates the supported legacy exports.
Release builds exclude `native_examples` test executables, strip the installed
ELFs, check their architecture, and fail if a product is still a library or
its real binary/resources are missing.

The development dependency must be the published, digest-pinned SDK/runtime/
toolkit artifact resolved by
[`platform_dependency.py`](../tools/platform_dependency.py). Release tests and
native builds explicitly refuse the old OS-source pin. They neither build the
OS nor import private OS implementations. A new compatible App version does
not require a matching OS release; only a new public platform interface does.

Focused tests build real `.deb` archives and use generated fixture signing keys.
APT state, dpkg roots, logs, caches and harmless package files stay in explicit
`build/` fixture roots. Tests cover deterministic ownership, identity partitions,
library dependencies, packaged public MCP, install/upgrade preservation,
bounded file takeover, stale metadata, bad signatures, mutated payloads,
version collisions/regressions, retained products and by-hash indexes. They
never install fixture packages on the developer's real root or call live AI.
Native unit/build/resource coverage is not interactive desktop or hardware
acceptance.
The packaged Doc/KV fixture selects the verified `python-sdk` and
`python-runtime` exports explicitly; common support comes from the actual App
package, not the SDK fixture. A test-only prepared artifact repository can be
selected inside `pytest.MonkeyPatch`, using cache-only `prepare_exports` with
downloads refused and restoring the module root afterward. This leaves the
production lock unchanged. Passing an older interoperability probe does not
establish availability of later schema/Rust API changes or unified Host behavior.

## Release workflow

[`release-apps.yml`](../.github/workflows/release-apps.yml) is manually dispatched
or reusable via `workflow_call`; it publishes reviewed `main` only:

```bash
gh workflow run release-apps.yml --repo xiaoyu-work/clawos-app \
  -f select=files -f version=1.2.3 -F initialize=false
```

Use `select=all` and `initialize=true` only for the first channel publication.
The initial OS image needs the support, sets and their selected dependencies
available; later independent releases normally select just the changed product.
Product/capability tests run before packaging, and graphical selections require
both native architecture jobs. The signing job receives their exact build
records and rejects missing, extra or mismatched package/architecture artifacts.
No release workflow invokes an OS build.

The local publication equivalent, **after** the build/test matrix and only from
a clean committed checkout, is:

```bash
# Configure the two signing secrets securely in the environment, not argv.
python3 tools/release_publish.py publish --plan build/release-plan.json \
  --artifacts build/release --output build/apt-publication
python3 tools/release_apt.py verify --repository build/apt-publication
```

Only the first command publishes GitHub content. `release_apt.py compose` is a
local assembly/verification primitive; its `--initialize` is not proof of a new
remote channel. The publication entrypoint additionally authenticates the
repository and checks that neither prior APT state nor previous App releases
exist before allowing initialization. HTTP/signature/freshness failures never
become empty-repository success.

Each selection gets an immutable tag:

- `app-files-v1.2.3`
- `cap-http-v1.2.3`
- `support-v1.2.3`
- `sets-v1.2.3`

Debian's prerelease `~` becomes `-` in the Git tag (Git forbids `~` in refs).
Such GitHub releases are marked prerelease, but publishing them still updates
the same APT channel; choose a preview version only deliberately.

Its assets are the actual `.deb` files, any selected development/interface archives,
`release.json`, `SHA256SUMS` and `SHA256SUMS.asc`. Packages carry
`X-Claw-Product`, `X-Claw-Source-Kind`,
`X-Claw-Variant`, `X-Claw-App-Ids`, `X-Claw-Runtime-ABI` and
`X-Claw-Source-Revision` control fields. Per-package installed metadata lives
at `/usr/share/clawos-app/packages/<package>.json`. The package version is the
distribution version; App manifest/XPI schema versions are not rewritten.

Releases are created as drafts, populated, then published and checked for
GitHub-enforced immutability. Existing tags cannot be rebound; an existing
immutable release is reused only after its pinned-key signature and every
asset match. There is no `--clobber` or forced tag push. An incomplete draft or
orphaned tag requires operator investigation and a new release version rather
than silently replacing its bytes.

## Retired Notifications config/util release input

**Current product metadata declares no native library exports.** Notifications
releases therefore emit no interface archive, and direct export requests fail
explicitly instead of reintroducing product UI/config libraries. Earlier
candidate archives are historical compatibility fixtures, not production inputs.
The real release path records `interfaces: null` in signed `release.json` and
does not include a config/util archive in the signed checksum set.
Release build/signing modules no longer import the retired exporter. Nonempty
legacy interface records and `.tar.gz` interface artifacts are rejected before
publication, even when supplied explicitly. Restoring config/util
`native_libraries` declarations fails before package writes and also fails
development-fixture preparation.

The replacement is OS-defined
`claw-os-sdk/rust/notification-presentation`, included by the existing recursive
`rust-sdk` platform export. Its optional `dbus` feature carries normalized
presentation data through additive `com.clawos.NotificationPresentation1` on
the existing private P2P channel. Native-owner checks report the OS panel and
notification applet build/test without App config/util or an interface tree.
That is source-boundary evidence, not a published SDK pin or complete runtime
authority acceptance.

The App retains its private config/util crates and `native_packages`, original
configuration/theme/markup/image preparation, and legacy protocol compatibility
for old OS versions. New OS consumers require presentation v1. Private FD names
and local `do_not_disturb` storage/meaning remain unchanged; this is not a core
DND or user-data migration.

The historical `release_interfaces.py` source and existing artifact bytes are
preserved, but its CLI now fails explicitly without creating output. Positive
release/fixture expectations for config/util exports have been replaced by
retirement regressions; rehashed fixture metadata cannot reintroduce the
declarations or payload trees. No `build/app-interfaces` alias is restored. Final SDK
publication/pinning remains parent-owned. No source checkout, private library
import, probe pin, cache mutation or unverified fallback is permitted.
The existing business-name gate is a blocker above, not the final integration
rule. No runtime package depends on or fetches an interface archive.

## Optional development and integration fixture archives

When `fixtures=true` is explicitly selected, each selected release also publishes
`claw-app-development-<sha256>.tar.xz`. `release.json` references it through
`development` with `format`, `selection`, `version`, `source_revision`,
`filename`, `sha256` and `size`. The archive and descriptor are covered by the
same signed `SHA256SUMS` as the Debian assets and protected by the immutable
Release. The architecture-independent build job produces it once; the signer
only verifies/copies it and never executes App staging or extension builders.

The archive has no enclosing directory:

```text
manifest.json
LICENSE
tools/stage.py
tools/package_assets.py
shared/python/
products/<selected-or-Python-dependency>/
capabilities/<selected-or-Python-dependency>/
payload/usr/lib/cos/apps/<selected-identities>/
payload/usr/lib/cos/python/
interfaces/<explicit-native-library>/
```

The manifest format is `claw.app-development/v1`, with
`purpose: development-and-integration-fixtures`. Its `groups` record source
kind, name, path, App IDs and `role` (`selected` or `python-dependency`).
`groups[].source_package` preserves the original complete package declaration.
Each archived `package.json` is the corresponding **staging projection**:
original Apps, kinds, Python exports/dependencies and extension/installed-asset metadata, but
no native product build metadata. The complete declared App trees, named
Python exports and required extension builder/assets accompany that projection.
Thus Doc's archive includes its declared Files dependency rather than an
incomplete or falsely Doc-owned parser. Only selected identities enter
`payload`; dependency owners' Apps are not installed there.

`tools/stage.py`, `tools/package_assets.py` and `shared/python` preserve the public
source/staging contract. The manifest names the canonical `stager` and its
`asset_helper`; the stager invokes the helper once. Common support still uses
the explicit `stage.py --shared` command. To restage Browser completely, run
`python3 tools/stage.py browser --root <destination>` with the optional `--apps`
selection. The asset helper's standalone CLI is for asset-only staging, not a
second pass over an already staged product. Neither downloads SDK/OS sources.
The ready-staged `payload` additionally carries packaging-owned pure Python
dependencies, including the licensed PPTX dependency when Files is in the
source closure. SDK/runtime, platform downloaders, OS implementations, native
product implementations, build trees and test executables are absent. Supply
the OS candidate's SDK/runtime when running integration fixtures; native
process tests must use the real `.deb` binary rather than compile product UI
from this archive.

`manifest.json.native_interfaces` maps each exported Cargo identity to
`path`, `package`, `version` and product `owner`. Current Notifications fixtures
have an empty export map. Historical compatibility identifiers were:

- `interfaces/cosmic-notifications-config`
- `interfaces/cosmic-notifications-util`

These two exports are retired: current fixture preparation and verification
reject their declarations and unowned `interfaces/` payloads. Historical bytes
remain available for investigation, not release or OS consumption. Any other
explicitly declared data-only compatibility export retains the existing checks
against executables, build hooks, proc macros, inherited product workspace
metadata and undeclared path dependencies. OS consumers must use the public
presentation SDK rather than compile Notifications product implementation.
Files, modes and symlink
targets are inventoried; deterministic tar metadata and the filename digest
bind the complete bounded archive.

To build only App fixture archives locally, without retired config/util exports:

```bash
python3 tools/release.py plan --select notifications,capability:document-engine --version 1.2.3
python3 tools/release_development.py --plan build/release-plan.json \
  --output build/development-archives
```

OS integration/development tooling should pin the immutable Release URL and
archive SHA256 and validate the manifest/file inventory. This is a development
dependency only: no App `.deb`, metapackage or installed-system update requires
the archive, and it never enters the APT pool or image payload.

## APT channel and refresh

The App channel is separate from the OS channel:

```text
https://xiaoyu-work.github.io/clawos-app/
  archive-key.asc
  dists/trixie/InRelease
  dists/trixie/Release
  dists/trixie/Release.gpg
  dists/trixie/catalog.json
  dists/trixie/main/binary-{amd64,arm64}/Packages[.gz|.xz]
  dists/trixie/main/binary-{amd64,arm64}/by-hash/{SHA256,SHA512}/<digest>
  pool/main/<package>/<package>_<version>_<architecture>.deb
```

The signed `app-apt` branch retains repository content between deployments.
Publication verifies the exact previous commit's signatures, identity, bounded
freshness, catalog, package bytes and all indexes before merging a selection.
Previous products, versions and by-hash indexes are retained. Same
name/version/architecture with changed bytes, or a lower version than already
published, is refused. Completed immutable Release tags also guard version
ordering if an earlier run uploaded assets but failed before its APT push.
An ordinary non-forced fast-forward push protects
against concurrent state changes. Pages deploys only the verified output.

`Release` includes SHA256/SHA512 indexes, `Acquire-By-Hash: yes`, `Date`, and
`Valid-Until` bounded to fourteen days. Both `InRelease` and detached
`Release.gpg` must authenticate the same content. APT freshness and signature
checks remain enabled.

[`release-refresh.yml`](../.github/workflows/release-refresh.yml) runs Monday
and Thursday at 06:23 UTC, or manually. It authenticates and re-signs the
retained metadata without rebuilding/releasing Apps or changing package bytes.
It shares publication concurrency with App releases. Monitor failed/disabled
schedules: expired or corrupted previous state requires explicit operator
recovery from authentic Release assets and a complete verified repository,
not disabling freshness or initializing over lost history.

The current retention policy never deletes another product or old payload.
Publication fails **before creating new Releases** if retained content exceeds
the 1 GB Pages limit or an individual `.deb` reaches GitHub's 100 MB Git-blob
limit. Moving hosting or introducing a reviewed, freshness-safe retention policy
is required before those limits; packages are never truncated or replaced by
source/test archives.

## Maintainer prerequisites

Before dispatching the first release:

1. Publish the platform-development artifact and commit its validated App lock.
2. Coordinate the `1:0.3.0` file-ownership boundary and versioned virtual
   runtime/service `Provides` in the OS packages.
3. Enable **immutable releases** in the App repository. The workflow verifies
   GitHub's setting before writing release content and verifies each published
   release is immutable.
4. Configure GitHub Pages with **GitHub Actions** as its source. Protect `main`
   and the `app-apt` state branch against force pushes/deletion while allowing
   this workflow's normal state commits.
5. Configure dedicated secrets `CLAW_APPS_APT_SIGNING_PRIVATE_KEY` and
   `CLAW_APPS_APT_SIGNING_PASSPHRASE`. Use a signing-enabled key matching
   [`archive-key.asc`](../packaging/apt/archive-key.asc) and fingerprint
   `ADBA1957E712B6C80B4CC8736C044D6F411416AF`. Never put private material in a
   repository, command argument, log, workflow artifact or release asset.
6. Restrict the `app-release` environment to reviewed `main` deployments.
   Its scheduled metadata refresh must not stall behind unattended mandatory
   approvals until `Valid-Until` expires. The Pages deployment uses
   `github-pages`; publication needs `contents: write`, and deployment needs
   `pages: write` / `id-token: write`.

The signer imports into a private project-local GnuPG home, checks the primary
key fingerprint, supplies passphrases only through stdin/file descriptor, and
removes its private workspace/agent afterward. Verification has only the
checked-in public key. Missing signing material or an unexpected key is an
error, never an unsigned fallback.

Adding these workflows does not itself publish a package. Inspect successful
Release and Pages runs, verify the installed system's APT update, and perform
the separate real desktop acceptance before claiming a production rollout.
