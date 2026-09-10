# App Release Packaging

This directory owns the independent App distribution contract, not OS image
construction or a privileged updater.

- `release.json` is the package/channel, native toolchain, public service ABI,
  Python dependency and bounded first-ownership-transfer policy.
- `apt/archive-key.asc` is the checked-in App archive public key. Its fingerprint
  must match both `release.json` and the OS repository consumer. Private signing
  material belongs only in the two dedicated GitHub Actions secrets.
- `../tools/release.py` builds exact kinded App payloads as real Debian packages;
  `release_apt.py` retains and authenticates the complete repository;
  `release_publish.py` handles immutable Releases, state commits and refresh.
- `../tools/native_payload.py` consumes original native installer output,
  prepares complete package-local App executables/resources/licenses and emits
  only common-Host compatibility launchers. Its unsigned preparation is input
  to the existing public signer, not a replacement signature or runtime grant.
  Settings authority files and unsupported auxiliary/activation exports fail
  explicitly; [native runtime/resource gates](../docs/native-payloads.md) remain.
- `../tools/release_payload.py` rejects App root hooks, authority/state/grant
  payloads and privilege-bearing metadata independently of origin/language.
  Signatures authenticate bytes, not runtime permission. New publication remains
  gated on the pending general App Host/capability/resource-owner contract.
- `../tools/release_snapshots.py` packages complete, separately authenticated
  `claw.provenance/v1` App directories and signs a manifest/artifact-bound catalog.
  It calls the existing pinned public verifier and has no OS-source dependency,
  root hooks, installer, permission summary or approval store. OS protected
  install/update review and activation remain prerequisites; Debian/APT is
  compatibility delivery, not a bypass. Operation/GUI and MCP/background entry
  binding follows the public manifest defaults, while `needs[].why` and scope
  requests remain unchanged data for OS-owned review and enforcement.
- `../tools/release_development.py` assembles the complete declared fixture
  staging closure and explicitly exported compatibility crates as a
  digest-addressed development archive; it is never a runtime dependency.
- `../tools/release_interfaces.py` is disconnected from active build/signing
  paths and its retired CLI fails explicitly. Config/util declarations,
  interface release records and fixture payloads cannot restore the old export.
  The replacement presentation protocol is OS-defined and travels in the
  existing public Rust SDK export, not an App interface archive.
  Historical candidates are not generic UI-free platform interfaces.
  Source fixtures remain opt-in.
- `../tests/release/` validates real dpkg/GnuPG/isolated APT behavior and packaged
  public MCP without modifying host packages or owner data.

See [Independent App releases](../docs/releases.md) for commands, names,
metadata, migration bounds, workflows and deployment prerequisites. Never
relax signatures/freshness, reuse an immutable version with changed bytes,
merge grants, duplicate another package's Python export, or claim a native
library/source archive is an installable native application.
