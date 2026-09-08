# Clipboard provenance

The `panel-clipboard` launcher, manifest and complete native
`claw-applet-clipboard` library were moved from Claw OS commit
`53ea0ff7aa9f8ff858588deab6dae1fec58cdee8`.
The native code is a GPL-3.0-only Claw OS addition to its COSMIC applets fork,
originally based on `pop-os/cosmic-applets` commit `89a149034d06`.
The original GPL license is preserved verbatim in [`native/LICENSE`](native/LICENSE),
along with source SPDX notices.

This repository owns presentation, CopyQ scripts and bounded subprocess adapter,
localization, desktop entry and tests. The unused standalone main is replaced
by the existing OS `cosmic-applets` host, which injects the policy callback.
The shared OS policy implementation is not copied and no other App is imported.
All original visual and CopyQ behavior is retained; this relocation does not
merge selection/history state or broaden grants.

Native development uses only the immutable shared toolkit source specified in
[`platform.lock.json`](../../platform.lock.json), with its existing licenses,
through [`tools/native_build.py`](../../tools/native_build.py) and the shared
[toolkit patches](../../tools/native-patches.toml). Installed launch identity,
desktop package ownership and signed OS updates remain unchanged.
