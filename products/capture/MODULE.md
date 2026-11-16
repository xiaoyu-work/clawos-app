# Capture Product

| Path | Responsibility |
| --- | --- |
| `apps/cosmic-screenshot/app.json` | One MCP tool, fixed native identity and separate screen/output grants |
| `native/cosmic-screenshot/src/main.rs` | Original interactive/modal/notify CLI and translations; shared non-interactive OS client |
| `native/cosmic-screenshot/src/gui.rs` | Published-SDK generic clients for private per-window OS portal status and source-bound notifications; no user bus or file access from returned metadata |
| `native/cosmic-screenshot/src/mcp.rs` | Strict pre-service arguments and manifest-bound authenticated MCP |
| `native/cosmic-screenshot/src/localize.rs` | Original embedded notifications in 72 locales |
| `native/cosmic-screenshot/test/unit/` | CLI, strict correlated GUI outcomes, argument validation and localization regressions |
| `native/cosmic-screenshot/test/support/portal.rs` | Fixture-only private D-Bus portal; no display or live capture |
| `native/test_process.py` | Real installed resources/binary and published-SDK MCP/GUI/notification clients against an isolated fake OS wire, with no user bus |
| `package.json` | Descriptor/native source, fixture example and process-test declarations |

The original standalone ashpd/zbus/Tokio graph, release profile and lock remain
independent of the shell toolkit. This crate has no libcosmic renderer,
file-chooser dependency, bundled font or optional Cargo feature to substitute.
Only the allowlisted immutable SDK/runtime inputs come from `platform.lock.json`.
Generated inputs belong under `build/capture-native`, not another checkout.

The OS owns capture permission, authenticated session selection, its portal
helper, deadlines, output-directory pinning, non-overwriting persistence
and task snapshots. Non-interactive CLI and MCP share that OS service,
not another App. Human-only interactive requests use the common Host's private
per-window OS request/status path through the existing SDK generic CLI helper.
The signed GUI explicitly requests screen capture and notification permission
through normal Root approval, never MCP's destination-write needs. Destinations
and clipboard actions remain in the OS portal; their user settings do not move.
File results are display metadata only and are never opened or moved by the App.
Non-interactive output still requires separate exact directory-write authority;
GUI declarations do not manufacture that permission from CLI arguments.

Root retains a single correlation and immutable modal choice per window,
checks the original live GUI lease without a short human-response timeout, and
cancels on stop/revocation/logout. Only the OS helper's terminal portal Response
or acknowledged Close plus checked process exit can retire that request;
uncertain cleanup remains pending. Clipboard success and cancellation remain
different outcomes. `--notify` retains the original localized text, icon,
transient presentation and five-second timeout through the generic sealed
App/source Notification Service. There is no direct D-Bus fallback.

From the repository root on Linux/WSL:

```sh
python3 tools/test.py capture
python3 tools/native_build.py capture test
python3 tools/native_build.py capture build
python3 products/capture/native/test_process.py
```

The process runner requires the existing `just` installer and a verified public
platform cache. It installs only into an isolated build fixture and supplies a
fake controlled OS wire, not capture/permission authority. The matching OS
Capture tests separately exercise the real non-root helper and private portal.
No live desktop, user image or installed state is accessed.
The process runner also accepts `--binary <built-binary> --source <native-inputs>`
to exercise an OS-composed build from the same immutable source.

The native payload binds both declared surfaces to real
`bin/cosmic-screenshot`, retaining resources/licenses. Its compatibility
command enters `cos app cosmic-screenshot --gui`, never the ELF directly.
The native Clap parser consumes one leading Host selector only in GUI mode,
preserving its original defaults, boolean/value syntax, save-path bytes,
help/version, errors and MCP-first ordering. CLI early exits precede localization;
MCP retains its existing localization initialization. The focused parser filter is
`native_gui_argv_` in `test/unit/main.rs`.
Both OS providers use their own gated `clawd` helper, never this App's
compatibility launcher. The obsolete hidden `--portal-capture-stdout` mode now
refuses explicitly, rather than contacting a user bus from ordinary App code.
This does not establish physical portal/display, installed-package or whole
native acceptance; see [native payloads](../../docs/native-payloads.md).
