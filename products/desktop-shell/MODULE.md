# Desktop Shell

## Responsibility

Own the complete, locally editable Caelestia desktop presentation and its
source-level CLI and Material shape dependencies. Keep QML layout, visuals,
native UI extensions, its bundled Quickshell engine and presentation resources
together. The engine is not an OS shared runtime.

The product declares the GUI-only `desktop-shell` App and its CMake native
payload. It is not yet the activated desktop session.
Do not treat an upstream installer or direct executable launch as completed
Claw runtime integration.

## Key files

| Path | Purpose |
| --- | --- |
| `upstream.lock.json` | Exact imported source trees and matching Quickshell dependency |
| `PROVENANCE.md` | Origins, revisions and license obligations |
| `native/caelestia/CMakeLists.txt` | Original shell and native-plugin build |
| `native/CMakeLists.txt` | Single staged ELF/resource assembly from all three native builds |
| `package.json`, `apps/desktop-shell/app.json` | GUI-only App, normal capability needs and private native resources |
| `native/caelestia/services/Hypr.qml` | Broker-backed window, workspace and output presentation |
| `native/caelestia/plugin/` | Original native C++ QML extensions |
| `native/caelestia/plugin/cmake/libcava.cmake` | Build adapter for the pinned waveform DSP core |
| `native/caelestia/plugin/3rdparty/libcava/` | Complete MIT libcava 1.0.0 source and notices |
| `native/caelestia-cli/` | Complete upstream CLI source |
| `native/m3shapes/` | Complete upstream Material shape source |
| `native/quickshell/` | Complete LGPL engine source, bundled with this App |
| `native/quickshell/src/main.cpp` | Common-Host GUI selector and read-only resource adapter |
| `native/caelestia/utils/scripts/desktop_control.py` | Closed desktop state and actions through the published SDK/kernel transport |

Managed GUI mode accepts only `--gui` and requires the Host's absolute
`COS_APP_RESOURCE_DIR`. It selects the bundled shell and QML modules there,
not the working directory, an ambient Quickshell config or caller-supplied
CLI paths. `COS_APP_GUI` chooses parsing behavior, never identity or authority;
Root still owns the authenticated launch and its whole lifetime.
Outside GUI mode, the original CLI remains available for source development.

## Boundaries

The OS retains the Agent, authenticated display/session lifetime, compositor
enforcement, App Host, capability decisions and authoritative system state.
Replacing the visual shell must not replace those services with upstream
notification history, raw system commands or a second permission mechanism.
Ordinary Apps do not need to be rewritten in QML.

The launcher reads the public desktop catalogue but never executes its command
strings or a configured terminal directly. It sends one exact AppID to the OS
desktop service through the published SDK and the fixed `cos` binary. The
selected GUI still needs the ordinary exact `desktop.launch` grant; a click,
catalogue entry or successful client startup supplies no authority. Denied or
indeterminate requests have no raw-execution fallback or automatic retry.
Launch frequency changes only after the broker confirms the request.

The notification drawer and popups consume the common Host's leased
`notifications.presentation` resource through the fixed SDK client. The
shell does not start a D-Bus notification server or persist `notifs.json`.
Dismiss and default acknowledgement are separate broker effects; hiding a
popup does not acknowledge the OS notification. Popup mute is a presentation
preference separate from the OS delivery policy.

The workspace bar and window controls consume Root's closed desktop channel.
Window mutations use its epoch-bound IDs, never native addresses. The bundled
engine does not build Hyprland's raw IPC client; Layer Shell and focus grab
remain separate, live capability-gated Wayland protocols. Capture opens the
existing signed Capture App, and window information uses icons and metadata
rather than a screen-capture grant.

Any later launch/payload integration must use the repository's existing
native App packaging and public SDK/runtime contracts. The original source
licenses, notices, file modes and resources must remain available.

## Validation

The initial source import is checked against the Git tree IDs recorded in
`upstream.lock.json`, including executable modes and every tracked file.
Those are baseline identities, not hashes that should be rewritten when
making intentional Claw modifications. Native compilation and actual
managed-GUI acceptance are separate required checks before activation.

The native plugin requires Qt 6.9 or newer, libqalculate, PipeWire, Aubio,
FFTW and lm-sensors development files. The pinned libcava DSP core is built
in-tree; the unrelated distribution `cava` terminal program is not a library
substitute or a runtime dependency. Its build adapter does not authorize audio
capture or bypass the OS resource boundary.
The launcher also needs the Qt SQLite runtime driver (`libqt6sql6-sqlite` on
Debian/Ubuntu); linking Qt Sql alone does not provide that plugin.

Run from a Linux-filesystem checkout of this repository:

```sh
cmake -S products/desktop-shell/native/caelestia -B build/caelestia -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DVERSION=1.0.0 \
  -DGIT_REVISION="$(git rev-parse HEAD)" -DDISTRIBUTOR=Claw \
  '-DENABLE_MODULES=plugin;shell'
cmake --build build/caelestia --parallel 4
cmake -S products/desktop-shell/native/m3shapes -B build/m3shapes -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DM3SHAPES_BUILD_EXAMPLES=OFF
cmake --build build/m3shapes --parallel 4
```

Both native build graphs compile with Qt 6.10.2. This does not establish a
running Quickshell frontend, managed GUI hosting or an installed desktop.
The bundled engine also builds with its original rendering code. Actual ELF
checks cover upstream CLI compatibility, GUI argument/resource refusals and
selection of a private synthetic QML resource independently of cwd and ambient
config. This is entry-adapter coverage, not authenticated desktop acceptance.

The unified build assembles one real engine ELF and the original private QML
libraries/resources without installing an OS runtime or upstream system hooks:
use a fresh staging destination, as the package producer does.

```sh
cmake -S products/desktop-shell/native -B build/desktop-shell -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DGIT_REVISION="$(git rev-parse HEAD)"
cmake --build build/desktop-shell --parallel 3
DESTDIR="$PWD/build/desktop-shell-installer" \
  cmake --install build/desktop-shell --prefix /usr
```

The standard producer also supports this CMake product:

```sh
python3 tools/native_build.py desktop-shell build --release \
  --app-root build/desktop-shell-app
```

This prepares the ordinary unsigned App payload for the existing signer; it
does not install the App, grant its needs or activate the desktop session.

Engine dependencies follow the vendored Quickshell CMake files, including Qt
Wayland/private headers, Wayland protocols 1.41+, CLI11, jemalloc, libunwind
and zstd. The source-pinned crash libraries build inside the engine.
The installed assembly passes the existing owned-tree/ELF/mode checks and
loads its real private Caelestia and Material Shapes modules without global
resource activation. App registration, protected services and authenticated
desktop acceptance remain separate gates.
Development artifacts retain the build host ABI. The current native check
requires glibc 2.43 and Qt/private ABI 6.10.2; it is not an artifact for an older
OS base. Target-ABI builds and explicit runtime plugin delivery remain release
prerequisites, not a reason to weaken dependency or update gates.
Each native component owns a freshly cleared build-staging directory, so an
incremental build cannot retain deleted presentation resources or helpers.
