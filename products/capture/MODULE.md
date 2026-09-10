# Capture Product

| Path | Responsibility |
| --- | --- |
| `apps/cosmic-screenshot/app.json` | One MCP tool, fixed native identity and separate screen/output grants |
| `native/cosmic-screenshot/src/main.rs` | Original portal/CLI/notification flow; shared non-interactive OS client and bounded native pipe mode |
| `native/cosmic-screenshot/src/mcp.rs` | Strict pre-service arguments and manifest-bound authenticated MCP |
| `native/cosmic-screenshot/src/localize.rs` | Original embedded notifications in 72 locales |
| `native/cosmic-screenshot/test/unit/` | CLI, argument validation, PNG input and localization regressions |
| `native/cosmic-screenshot/test/support/portal.rs` | Fixture-only private D-Bus portal; no display or live capture |
| `native/test_process.py` | Real installed resources/binary, fake broker/portal, MCP and human selection paths |
| `package.json` | Descriptor/native source, fixture example and process-test declarations |

The original standalone ashpd/zbus/Tokio graph, release profile and lock remain
independent of the shell toolkit. This crate has no libcosmic renderer,
file-chooser dependency, bundled font or optional Cargo feature to substitute.
Only the allowlisted immutable SDK/runtime inputs come from `platform.lock.json`.
Generated inputs belong under `build/capture-native`, not another checkout.

The OS owns capture permission, authenticated session selection, the fixed
native process, deadlines, output-directory pinning, non-overwriting persistence
and task snapshots. UI and MCP share the non-interactive service and native
portal implementation, not another App. Human-only interactive destinations
and clipboard actions remain in the OS portal; their user settings do not move.

From the repository root on Linux/WSL:

```sh
python3 tools/test.py capture
python3 tools/native_build.py capture test
python3 tools/native_build.py capture build
python3 products/capture/native/test_process.py
```

The process runner requires the existing `just` installer and `dbus-daemon`;
it installs only into an isolated build fixture and starts a private fake
portal. No live desktop, user image or installed state is accessed.
The process runner also accepts `--binary <built-binary> --source <native-inputs>`
to exercise an OS-composed build from the same immutable source.

The native payload binds both declared surfaces to real
`bin/cosmic-screenshot`, retaining resources/licenses. Its compatibility
command enters `cos app cosmic-screenshot --gui`, never the ELF directly.
This does not establish the OS provider's `--portal-capture-stdout` contract or
GUI argument/resource admission. Those paths remain gated rather than gain a
special launcher exception; see [native payloads](../../docs/native-payloads.md).
