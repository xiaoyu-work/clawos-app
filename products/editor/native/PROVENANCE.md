# Native Editor provenance

`cosmic-edit/` preserves the complete Claw OS fork of
[`pop-os/cosmic-edit`](https://github.com/pop-os/cosmic-edit),
upstream revision `7bbe82ec3f2b`, GPL-3.0-only as declared in its Cargo manifest.
It was relocated from `claw-os/desktop/edit` at OS revision
`8f226f08b7e18ae476a7a5655c111d35d99be1d7`.
The original license, copyright notices, translations, icons, screenshots,
Debian packaging, development files and executable modes are retained.

The existing upstream libcosmic, cosmic-files file-chooser library,
cosmic-syntax-theme and cosmic-text dependencies remain pinned by the native
Cargo.lock. This migration does not substitute a toolkit or move the Files App.
OS SDK/runtime are development dependencies from the immutable platform lock;
OS composition resolves the same library boundaries from its source tree.
No OS filesystem, snapshot, model-provider or authorization implementation
is copied into this product.
