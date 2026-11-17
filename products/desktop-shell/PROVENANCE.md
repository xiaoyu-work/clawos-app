# Desktop shell provenance

These are complete source imports, not submodules or build-cache references.
Source files, native plugins, resources, documentation, build metadata,
licenses and executable modes are retained. The libcava import excludes its
unrelated Android signing keystore; that file is not Linux source or a build
dependency.

| Local source | Upstream | Revision | License |
| --- | --- | --- | --- |
| `native/caelestia/` | <https://github.com/caelestia-dots/shell> | `e72df8eb687246aa6c6ec6daa631073b374e5215` | GPL-3.0 |
| `native/caelestia-cli/` | <https://github.com/caelestia-dots/cli> | `9ab901f592917454da396ea012c50dd2c3f37003` | GPL-3.0 |
| `native/caelestia/plugin/3rdparty/libcava/` | <https://github.com/LukashonakV/cava> | `f03278ef9e5e7948fb206453d2f02758f8db216c` (`1.0.0`) | MIT |
| `native/m3shapes/` | <https://github.com/soramanew/m3shapes> | `32ad9ce328bb77ed349b40a3be10ee9ea610b8ab` | Apache-2.0 |

The shell dependency revisions are selected by Caelestia's imported `flake.lock`.
Its exact Nix package set selects the libcava 1.0.0 fork above.
The original Git tree IDs are recorded in
[`upstream.lock.json`](upstream.lock.json). At import, the three local trees
match those IDs exactly, including file modes. They contain no Git submodules
or Git LFS pointer substitutions.

Existing whitespace in imported upstream files is retained through file-scoped
`.gitattributes` exceptions rather than rewriting the imported source or
license text. Claw-owned files retain the normal repository checks.

Quickshell itself is not copied into these directories. The matching
`9b0f339b19057f4731bf3b48293307d7ef241671` source is available from the
[official mirror](https://github.com/quickshell-mirror/quickshell) under
LGPL-3.0. Building that fixed dependency does not establish a Claw engine fork.
Qt and other upstream dependencies retain their own licenses.

Subsequent Claw modifications remain subject to the applicable source
licenses. Distribution must preserve notices and provide corresponding source
and other required materials; importing the source does not grant trademark
rights or permission to publish a release.

The Claw CMake adapter builds only libcava's original `cavacore.c` into the
native UI plugin, with FFTW. It does not build the terminal program or its raw
audio-input backends, download a library during configure, or substitute a
different Cava implementation. Retained library files and licenses keep their
original bytes; `excluded_files` records the keystore omission.

No Omarchy source, OS authority implementation, user configuration, credentials
or installed state is included in this import.
