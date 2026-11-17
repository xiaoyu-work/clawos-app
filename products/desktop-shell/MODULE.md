# Desktop Shell

## Responsibility

Own the complete, locally editable Caelestia desktop presentation and its
source-level CLI and Material shape dependencies. Keep QML layout, visuals,
native UI extensions and presentation resources together.

The current source baseline is not a registered or activated App. Existing
product discovery, release matrices and installed identities are unchanged.
Do not treat an upstream installer or direct executable launch as completed
Claw runtime integration.

## Key files

| Path | Purpose |
| --- | --- |
| `upstream.lock.json` | Exact imported source trees and matching Quickshell dependency |
| `PROVENANCE.md` | Origins, revisions and license obligations |
| `native/caelestia/CMakeLists.txt` | Original shell and native-plugin build |
| `native/caelestia/services/Hypr.qml` | Upstream compositor-facing presentation model |
| `native/caelestia/plugin/` | Original native C++ QML extensions |
| `native/caelestia/plugin/cmake/libcava.cmake` | Build adapter for the pinned waveform DSP core |
| `native/caelestia/plugin/3rdparty/libcava/` | Complete MIT libcava 1.0.0 source and notices |
| `native/caelestia-cli/` | Complete upstream CLI source |
| `native/m3shapes/` | Complete upstream Material shape source |

## Boundaries

The OS retains the Agent, authenticated display/session lifetime, compositor
enforcement, App Host, capability decisions and authoritative system state.
Replacing the visual shell must not replace those services with upstream
notification history, raw system commands or a second permission mechanism.
Ordinary Apps do not need to be rewritten in QML.

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
