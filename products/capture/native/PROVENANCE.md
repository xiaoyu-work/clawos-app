# Native Capture provenance

`cosmic-screenshot/` preserves every native file from
`claw-os/desktop/screenshot` at
`59aa74cdaef9d0408dc3ac27ffc7116fb7256b23`:
the standalone Cargo manifest/lock and release profile, complete portal client
and localization code, 72 Fluent locales, desktop entry, seven raster icons,
scalable SVG, hidden workflow/git inputs, justfile and Debian packaging.
There were no original crate-local Rust tests or symlinks; this migration adds
targeted unit and real-binary fixture coverage.

Upstream is [pop-os/cosmic-screenshot](https://github.com/pop-os/cosmic-screenshot)
at `b917c631d155`, under the preserved GPL-3.0 [license](LICENSE).
The original ashpd 0.12/zbus/Tokio dependency graph is retained. There is no
libcosmic toolkit/renderer, file chooser, font subtree or optional build feature
in this client. Its human UI is the existing OS portal, which stays OS-owned.
Direct libc/test tempfile dependencies support bounded PNG consumption and
fixture validation; no OS authority implementation is copied.
