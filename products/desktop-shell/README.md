# Claw desktop shell

The editable source baseline for Claw's Quickshell-based desktop interface.
It contains the complete Caelestia shell, matching CLI and Material shape
library, not an Omarchy distribution or a replacement Agent.

| Directory | Source |
| --- | --- |
| `native/caelestia/` | Complete QML shell, native C++ plugin, resources and upstream build files |
| `native/caelestia-cli/` | Matching Caelestia command-line implementation |
| `native/m3shapes/` | Matching Qt Quick Material shape library |

[`upstream.lock.json`](upstream.lock.json) records the immutable source
revisions and Git trees. The CLI, shape library and Quickshell revision match
the shell's original `flake.lock`. Original licenses and notices remain in
each source tree; see [provenance](PROVENANCE.md).

This commit establishes source ownership only. The product is not yet a
registered App, release input or installed session, and does not change the
existing App count. Native build, managed GUI admission and OS service
integration must be completed before activation.

Quickshell is a pinned runtime dependency, not an engine fork here.
Caelestia's native plugin requires Qt 6.9 or newer. Its upstream CMake build
also requires explicit `VERSION` and `GIT_REVISION` values when built outside
the original Git history; it must not infer them from this repository's tags.

Display login, compositor authorization, capabilities, notifications and
other authoritative services remain in `claw-os`. The frontend must use the
same signed App Host and versioned OS interfaces as other native Apps.
Source availability, UI identity and installation confer no authority.
