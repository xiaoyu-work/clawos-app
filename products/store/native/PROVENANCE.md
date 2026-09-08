# Native Store provenance

`cosmic-store/` preserves the complete 138 tracked-file fork and executable
modes from `claw-os/desktop/store` at OS revision
`036f4f8cbdd19f4f3a827e328a6a631af1093c39`.
Upstream is [pop-os/cosmic-store](https://github.com/pop-os/cosmic-store)
at `2c705e725e31`, with the original GPL-3.0 license and copyright notices.
Translations, icons, screenshots, Debian/Nix/build inputs, hidden files and the
`flathub-stats` nested workspace remain included.

The original standalone Cargo.lock, upstream libcosmic graph and default
Flatpak/PackageKit, logind, notification, Wayland and wgpu features are retained.
SDK/runtime are the immutable libraries selected by `platform.lock.json`;
no OS provider, authority implementation or installed state is copied here.
The native catalog embeds existing product functions, not a mutable helper or
App entrypoint. Human UI policies and OS package transaction identity remain
separate from this read-only MCP surface.
