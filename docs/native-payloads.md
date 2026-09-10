# Package-local native App payloads

This is the producer contract for Editor, Files, Terminal, Launcher, Store,
Media Player, Capture, Settings and Notifications. It is not permission to
publish or an assertion of GUI/resource integration acceptance.

Each product's `package.json` declares `native_payload.app`, its real
`program`, and any `auxiliary_programs`. These are build ownership declarations,
not an App type, trust tier, runtime command loader or privilege allowlist.
The selected App's existing identity, version, AI policy, MCP tools and complete
`needs` values remain unchanged.

## Preparation and signing

The nine manifests explicitly select `bin/<program>` for both `entry` and
`mcp.entry`, with `runtime: "binary"` and `desktop.exec: "--gui"`. The selector
is not an executable path or an argument injected into the native program.
One real ELF serves both surfaces without copying it twice.

[`native_payload.py`](../tools/native_payload.py) validates the original
installer's complete output before preparing a fresh App directory. It checks
the ELF header and executable load segment, architecture, executable mode,
single-link regular files, resource paths and original licenses. Scripts,
header-only placeholders, libraries, links, missing/unowned executables,
authority payloads and conflicting output are errors. Source Apps, original
installer bytes and caller data are not overwritten.

Run from the repository root on Linux/WSL:

```sh
python3 tools/native_payload.py notifications --plan

# Uses the real published platform.lock.json and the original product installer.
python3 tools/native_build.py notifications build --release \
  --target-dir build/native-package-target \
  --app-root build/prepared/cosmic-notifications

# Alternatively, consume an explicit original installer output under build/.
python3 tools/native_payload.py notifications \
  --installed-root build/notifications-installer \
  --app-root build/prepared/another-notifications \
  --architecture amd64
```

Preparation is explicitly **unsigned**. It does not invent `.provenance.json`,
change trust roots or supply a signer pin. Use the existing public provenance
CLI and an authorized App publisher key; pass each `entrypoints` value returned
by the plan once through `--entrypoint`. For these dual-mode Apps that is just
`bin/<program>`. The existing `claw.provenance/v1` signer inventories all files,
including full ELF bytes, resources and licenses. Named resource declarations,
when supplied, use that existing format and confer no mounts or grants.

Only after signing may this directory enter the existing
[verified snapshot/catalog producer](releases.md#verified-app-snapshot-producer).
The verifier checks each selected entry in both the signed entrypoint list
and the authenticated regular-file inventory. Manifest bytes, localized purpose
maps, conditions and argument associations remain exact; the permission-contract
digest is not a substitute for preserving those bytes.

The output contains:

```text
app.json                         exact source manifest bytes
bin/<program>                    real, single-link executable
bin/<auxiliary-program>          preserved file, not implicitly executable by a Host route
resources/usr/share/...          original installed resource bytes
LICENSE
licenses/...                     original native license/copyright/notice files
.provenance.json                 supplied only by the existing public signer
```

No SDK/runtime, common Python support, user configuration or state is copied
into this directory. Common imports remain the separately owned
`/usr/lib/cos/python` contract. There is no package-local venv/import activation.
Ordinary `tools/stage.py` still stages source; it does not fabricate missing
compiled binaries.

## Compatibility installation

`native_build.py build --release --install-root build/<destination>` runs the
same original installer privately, stages the App under
`usr/lib/cos/apps/<identity>/`, and exports the primary legacy program name
only as a fixed common-Host launcher:

```text
/usr/local/bin/cos app <identity> <desktop.exec> [original arguments...]
```

This is the public `cos app` route in the OS's
`core/src/router/app_commands.rs`, not `cos app run`, a direct ELF invocation
or an App-to-App call. Arguments remain distinct argv values; errors and exit
status are propagated. The launcher does not clear caller identity, manufacture
approval, choose another executable or fall back when the Host refuses.
Desktop and thumbnailer exports must target this program, not a shell or
alternate executable; D-Bus activation without a Host contract is refused.

The original resource files remain in the App snapshot and their legacy
desktop/icon/metainfo exports where supported. A file copied to
`resources/usr/share/...` does **not** map that file back to `/usr/share/...`
inside the Host. Runtime lookup, provider identity, display transport and
authorized resource access remain OS/product integration, not signer behavior.
The native Debian dependency scanner examines the package-local ELFs, never
the compatibility shell scripts.
Compatibility resource exports are limited to the original freedesktop
application/icon/metainfo/thumbnailer and COSMIC schema directories. An
uncontracted global path, such as an archive keyring, is rejected rather than
activated. Exports use the private prepared copy, not a mutable installer path;
empty resource directories and modes are retained inside the App.

## Deliberately gated surfaces

| Surface | Exact unresolved boundary |
| --- | --- |
| Native GUI arguments | The traced public router accepts trailing arguments, but `bridge::launch_gui` currently constructs an empty native argv and conveys them only as `COS_ARGS_JSON`. These programs parse native argv. Wrapper forwarding is preserved, but file/URI opens, Settings page selectors, Terminal flags, Capture modes and Player thumbnailing are not claimed working through this Host until the OS supplies the appropriate argument contract. |
| GUI permissions | The current GUI plan derives fixed/wild operation needs, not MCP-tool needs. Fixed requests outside launcher delegation are dropped without an approval prompt, and an unregistered launcher cannot acquire rights above Medium risk. A declared GUI selector operation expresses needs but does not acquire them. Preserve zero/denied rights until an explicit OS-owned authorization path is available; do not union MCP permissions or bootstrap Admin. |
| Files companion | The original installer also produces `cosmic-files-applet`. App-only preparation preserves its complete ELF under `bin/`, but the main manifest does not select that different executable. Compatibility installation refuses rather than retaining an unsandboxed secondary binary, choosing a new identity or inventing an auxiliary-entry ABI. |
| Settings authority files | The original installer supplies `usr/share/polkit-1/rules.d/cosmic-settings.rules` and `usr/share/polkit-1/actions/com.clawos.Settings.Users.policy`. Both remain rejected before output; neither is silently stripped or exempted. The package stays gated pending OS-owned authority integration. |
| Installed resources and state | Settings defaults under `/usr/share/cosmic`, legacy icon/theme lookup, global desktop catalogs and existing native XDG configuration are not automatically mapped into an App partition. No file or data migration is performed. |
| Provider/helper executable identity | Existing OS capture, media-player, Settings and presentation callers may still identify the legacy system program or require special argv/private descriptors. A Host-only wrapper is not the original ELF or a new grant. Parent-owned callers must bind the authenticated package-local resource; Capture's `--portal-capture-stdout` and Player's thumbnailer cannot be reinterpreted as generic GUI authority. |

The pending-origin-neutral publication gate remains enabled. Signature/archive
validity is deliberately separate from these runtime checks. Mail's opaque
stdio operation, Clipboard/GUI containment and OS review implementation are
outside this nine-native unit.

## Focused validation

```sh
python3 -m pytest -q tests/release/test_native_payload.py

python3 -m pytest -q tests/release/test_snapshots.py \
  -k real_native_package_local_signed_acceptance \
  --provenance-cos-fixture="$COS_BIN" \
  --provenance-cos-sha256="$COS_BIN_SHA256" \
  --native-settings-fixture="$SETTINGS_ELF" \
  --native-notifications-fixture="$NOTIFICATIONS_ELF"
```

The public test CLI must include the
[linear large-file SHA-256 fix](https://github.com/xiaoyu-work/claw-os/commit/9e1eaab088bc301963f1de3accf69bf6ac148e8f).
Older implementations repeatedly drain the front of a whole-file buffer and
must not be reused for these large native cases. The fix preserves the hashing
API, compression algorithm, digests and provenance format; no App-side hashing
or verifier fallback is needed.

Both full, unstripped Settings and Notifications fixtures have passed the
existing sign/verify, catalog, extraction, byte/mode/manifest preservation and
isolated MCP cases with an explicitly identified test-only CLI containing that
fix. This closes their signed-archive check, not a fresh release build, complete
Settings installer, GUI/resource/authority check or production tool pin.

For oversized debug fixtures, the explicit `--native-fixture-strip` test option
applies the release's existing `strip --strip-unneeded` step to a private copy.
The original fixture is untouched. The test compares every load segment and
its code/resource bytes before and after, excluding only section-table fields
in the ELF header, and records both full-file digests. This is a real
release-style ELF, not a substitute program or a claimed fresh optimized build.

Plan/copy/refusal tests use explicitly synthetic installer fixtures; they are
not native product acceptance. The optional real cases use the supplied
Settings/Notifications ELFs, actual manifest bytes and product resources,
existing App signatures, signed catalogs, archive re-extraction and isolated
MCP tool discovery. They do not connect to a desktop, provider or user bus.
The Settings positive archive fixture supplies real safe icon/schema/
application/metainfo source bytes, not its forbidden polkit payload. Complete
Settings installer rejection is a separate negative case, not hidden by that
archive fixture. Available prebuilt ELFs do not prove a fresh optimized build
or visual/resource/authority acceptance. Missing real inputs are explicit skips,
never replacement binaries or production pins.
