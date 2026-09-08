# Native Launcher provenance

`cosmic-launcher/` is the complete Claw OS fork of
[`pop-os/cosmic-launcher`](https://github.com/pop-os/cosmic-launcher),
upstream revision `1e57708e5af9`, GPL-3.0. It was relocated from
`claw-os/desktop/launcher` at OS revision
`8b5a323ddb84d7cf896d6514904f38f9b503f2f8`.
The original `LICENSE.md`, translations, resources, packaging, modes and
upstream development files are retained.

The OS-owned `pop-launcher` library/service (`desktop/launcher-backend`,
MPL-2.0, upstream `pop-os/launcher` revision `5b8685107166`) is not copied
into this product. Development uses the immutable platform lock, as it does
for the restyled toolkit and SDK/runtime. System composition supplies these
same dependency boundaries from its own source tree.
