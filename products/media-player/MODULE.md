# Media Player Product

| Path | Responsibility |
| --- | --- |
| `apps/cosmic-player/app.json` | Seven tools and separate exact observation/control grants |
| `native/cosmic-player/src/main.rs` | Original GStreamer/libcosmic UI and authoritative playback state |
| `native/cosmic-player/src/playback.rs` | Shared native state snapshots and typed UI commands |
| `native/cosmic-player/src/mpris_backend.rs` | Original MPRIS implementation, corrected name/Stop/status and live UI publication |
| `native/cosmic-player/src/mpris.rs` | Native subscription connecting the MPRIS backend to the existing UI event loop |
| `native/cosmic-player/src/mcp.rs` | Authenticated MCP, strict empty arguments, deadlines/cancellation and explicit installed OS client |
| `native/cosmic-player/test/unit/` | Actual backend commands, state/metadata and UI message mapping |
| `native/cosmic-player/test/support/mpris.rs` | Fixture-only private bus endpoints and synthetic native state |
| `native/test_process.py` | Installed binary/resources, isolated stdio MCP and fixture broker/native-MPRIS acceptance |
| `package.json` | Descriptor, native inputs, fixture executable and process-test declarations |

The native binary remains a standalone workspace with its original
`iced_video_player` / libcosmic renderer and optional feature graph.
The OS owns authentication, per-owner grants, executable identity, session
selection, dispatch gating, deadlines and audit. Product code imports only
the versioned SDK, not OS providers or other Apps. Native state is projected
from the UI, never a second MCP-only cache.

Run from the repository root on Linux/WSL:

```sh
python3 tools/test.py media-player
python3 tools/native_build.py media-player test
python3 tools/native_build.py media-player build
python3 products/media-player/native/test_process.py
```

The process fixture requires the existing `just`, `bubblewrap` and
`dbus-daemon` tools. It accepts `--binary <binary> --source <native-inputs>`
for an immutable OS-composed build, and `--cos-binary <cos>` to exercise the
actual installed-path CLI against its private broker fixture. The OS repository
owns provider/authority and authenticated dispatch tests. Fixtures never
open user files, start playback devices, or connect to a live desktop bus.

`native_payload` selects the real `bin/cosmic-player` for GUI/MCP and preserves
the original resources, thumbnailer metadata and licenses. The primary legacy
command enters the common Host; it does not bypass admission for thumbnailing.
URI/thumbnailer argv and existing OS playback executable/resource bindings
remain explicit runtime gates; see [native payloads](../../docs/native-payloads.md).
