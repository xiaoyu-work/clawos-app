# Native Terminal provenance

`cosmic-term/` preserves all 162 tracked files and executable modes from
`claw-os/desktop/term` at OS revision
`e9aa9b87f92d6d55e8466bc946bded9eef3bfdda`.
Its upstream is [`pop-os/cosmic-term`](https://github.com/pop-os/cosmic-term)
at `0a7fd0c26bf2`; the package declares GPL-3.0-only.
The original license, copyright notices, translations, themes, screenshots,
icons, Debian/Nix/build inputs, password integration and unit tests remain.

The original native Cargo.lock, upstream libcosmic/file-chooser libraries,
alacritty terminal and cosmic-text renderer graph are retained. This does not
substitute the OS's applet toolkit patches or remove the default renderer.
SDK/runtime remain pinned development libraries from `platform.lock.json`.
Native MCP compiles the existing Terminal command implementation into the
binary through a private library adapter. No OS provider, capability authority,
snapshot implementation or user state is copied into this product.
