# Calendar provenance

The `panel-calendar` launcher, manifest and native `claw-applet-calendar`
presentation were moved from Claw OS commit
`bd99720f99ea411df6833d6acccad1bf47d676ee`.
The native presentation is a Claw OS GPL-3.0-only addition to its COSMIC
applets fork. That fork originated at `pop-os/cosmic-applets` commit
`89a149034d06`; its unmodified GPL license is preserved in
[`native/LICENSE`](native/LICENSE), along with the source SPDX notices.

This repository owns the complete standalone Calendar executable, UI library,
localization, desktop entry, icon and native build/installer. The OS
`cosmic-applets` dispatcher no longer links the product or reads its resources.
The original callback seam now uses the public SDK's fixed, versioned OS
applet provider. Provider implementation and policy remain OS-owned; neither
Calendar nor Widget Rail calls another App.

Development links the shared Claw OS toolkit (including its vendored iced
tree) from the immutable [`platform.lock.json`](../../platform.lock.json).
Its source licenses and origin notices remain in that dependency. The
[`../../tools/native-patches.toml`](../../tools/native-patches.toml) mapping preserves the original
desktop workspace's toolkit patches, now carried by the standalone manifest.
No toolkit or OS authority implementation is copied. Independent native App
packages require the OS `claw-os-applet-services-v1 (= 1)` ABI, preserving
identities, user data and the original GPL terms.
