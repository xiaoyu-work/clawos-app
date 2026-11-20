# Desktop Shell

## Responsibility

Own the complete, locally editable Caelestia desktop presentation and its
source-level CLI and Material shape dependencies. Keep QML layout, visuals,
native UI extensions, its bundled Quickshell engine and presentation resources
together. The engine is not an OS shared runtime.

The product declares the GUI-only `desktop-shell` App and its CMake native
payload. The OS admits it as the shell of an authenticated login.
`release: false` excludes it from independent App Debian and Store releases.
Once its target ABI and authenticated launch are qualified, the separate
Desktop Shell build workflow supplies the signed payload embedded in
`claw-os-desktop`. `native/qt.lock.json` pins Qt 6.12.0 and
its published corrections. The unified CMake build compiles those sources
against the build host's ABI and uses them for every native child. Release
payloads must be built on Debian 13, not the Ubuntu preview environment.
The pinned Qt runtime is App-owned; Debian backports supply the Wayland
scanner and protocol XML needed to build Quickshell's background effects.
Do not treat an upstream installer or direct executable launch as completed
Claw runtime integration.

## Key files

| Path | Purpose |
| --- | --- |
| `upstream.lock.json` | Exact imported source trees and matching Quickshell dependency |
| `PROVENANCE.md` | Origins, revisions and license obligations |
| `native/caelestia/CMakeLists.txt` | Original shell and native-plugin build |
| `native/CMakeLists.txt` | Single staged ELF/resource assembly from all three native builds |
| `native/build-qt.py`, `native/qt.lock.json` | Verified Qt source build and App-private runtime staging |
| `package.json`, `apps/desktop-shell/app.json` | GUI-only App, normal capability needs and private native resources |
| `native/caelestia/services/Hypr.qml` | Broker-backed window, workspace and output presentation |
| `native/caelestia/services/Quiet.qml` | Shared light/dark palette, Dock window projection and private presentation preferences |
| `native/caelestia/modules/drawers/{TopBar,QuietMenu}.qml` | Per-output reserved top edge, Dock and locally anchored Quiet panels |
| `native/caelestia/plugin/` | Original native C++ QML extensions |
| `native/caelestia/plugin/cmake/libcava.cmake` | Build adapter for the pinned waveform DSP core |
| `native/caelestia/plugin/3rdparty/libcava/` | Complete MIT libcava 1.0.0 source and notices |
| `native/caelestia-cli/` | Complete upstream CLI source |
| `native/m3shapes/` | Complete upstream Material shape source |
| `native/quickshell/` | Complete LGPL engine source, bundled with this App |
| `native/quickshell/src/main.cpp` | Common-Host GUI selector and read-only resource adapter |
| `native/caelestia/utils/scripts/desktop_control.py` | Closed desktop state and actions through the published SDK/kernel transport |
| `native/caelestia/utils/scripts/desktop_review.py` | One reviewed menu selection or power action through the private GUI broker |

Managed GUI mode accepts only `--gui` and requires the Host's absolute
`COS_APP_RESOURCE_DIR`. It selects the bundled shell and QML modules there,
not the working directory, an ambient Quickshell config or caller-supplied
CLI paths. `COS_APP_GUI` chooses parsing behavior, never identity or authority;
Root still owns the authenticated launch and its whole lifetime.
Outside GUI mode, the original CLI remains available for source development.

## Boundaries

The OS retains the Agent, authenticated display/session lifetime, compositor
enforcement, App Host, capability decisions and authoritative system state.
The bundled Quickshell build does not provide a separate polkit agent.
Replacing the visual shell must not replace those services with upstream
notification history, raw system commands or a second permission mechanism.
Ordinary Apps do not need to be rewritten in QML.

The top Dock reads public desktop entries for labels and original SVG
artwork. Hover labels are single-line, click-through and sit below the bar.
It starts one `cos __desktop-events` connection per Shell, with an
initial snapshot and subsequent updates only on relevant changes. The Root
GUI Host reports managed Apps independently of window count. The Dock focuses
an existing epoch-bound window, otherwise it asks Root to reopen the
running App or start it if absent. Apps without reopen support do not get a
second copy when they are already running. A visible unmanaged window can
still be focused, but it does not establish a managed App lifetime.
Right-clicking an App pins it in the Shell's private data.
The permanent Launcher entry opens the independent
`claw-launcher` GUI; the Shell contains no launcher search.
`services/DesktopMenu.qml` sends one desktop entry ID through the existing
`desktop_review.py` and private GUI broker, never an Exec string. The Claw
mark sends the reserved Agent UI entry to the same broker, which handles it
only for the OS-started desktop Shell. This does not start recording or send a
model request. A submission does not prove a window appeared. Denial or
uncertainty has no raw-execution fallback or automatic repeat.

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

Audio controls observe and change the default input and output through the
existing OS audio provider. Device routing, volume and microphone mutations
remain independent optional permissions. The stream list is read-only and
the shell does not open the owner PipeWire socket for visualizers.

Brightness uses independent optional display observation and control rights.
The shell displays and changes a backlight only when the OS reports one
unambiguous output and backlight. It does not open DDC, I²C or backlight
devices, or guess which device belongs to an external monitor.

Audio and brightness skip observation without the corresponding optional
permission and leave unapproved controls disabled. `services/ShellState.qml`
uses the Host's startup projection in the order of `desktop.optional_needs`
in the signed manifest. This affects presentation only: Root still checks
live authorization for every request.

The unlocked session's Logout action exits this shell. The authenticated OS
session subscriber observes that exit and lets PAM retire the exact display
session. The App does not need authority to terminate a Linux user.

The Lock button and idle lock request use `ipc.invoke:desktop.session.lock`
through the private broker. The Shell no longer contains a lock renderer,
PAM conversation or unlock command. The OS owns the native lock for this
display and records acknowledgement after it has taken control. The OS
confirms that lock before dispatching sleep requested from the desktop menu.

The OS-started system menu sends the selected launch or power action to the
private GUI broker without a second confirmation. The broker binds each
request to the authenticated display and installed target. This does not
give the Shell a reusable `sys.power` or App-invocation grant. The Shell
reports failure, not completed shutdown or sleep.
The lock screen offers no power actions, and the battery monitor warns
without sending automatic hibernation requests.

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
The pinned Qt stage includes the SQLite, Wayland platform, and WebP plugins
and upstream notices. The WebP plugin decodes the bundled wallpaper using
Debian's `libwebp`. The ELF search paths are package-relative: Caelestia's
QML plugins find their backing libraries in `Caelestia/lib` and share the
App's private Qt. Qt's installed test modules and static object files are
excluded. No distribution Qt package or ambient plugin directory supplies
the managed runtime. The Material Symbols font is a signed private resource,
not a system font dependency.

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
Wayland/private headers, Wayland 1.25+, protocols 1.47+, CLI11, jemalloc, libunwind
and zstd. The source-pinned crash libraries build inside the engine.
The Debian 13 build with private Qt 6.12.0 produces the native installer tree.
An earlier Ubuntu preview loaded Caelestia and Material Shapes without global
resource activation; that preview used the Ubuntu ABI and is not the Debian
artifact. In a separate Debian 13 KVM guest, a locally signed App rendered
inside the ordinary GUI Host after actual greetd/PAM login and owner review.
The guest rendered the bundled icons, ran a separately signed Editor via an
owner shortcut, and confirmed checked Logout with both Apps open. With no
power grant, clicking Shutdown sent no request. The default launcher,
authorized power effects and release acceptance remain unverified.
Each native component owns a freshly cleared build-staging directory, so an
incremental build cannot retain deleted presentation resources or helpers.
