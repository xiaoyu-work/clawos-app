# Calendar provenance

The `panel-calendar` launcher, manifest and native `claw-applet-calendar`
presentation were moved from Claw OS commit
`bd99720f99ea411df6833d6acccad1bf47d676ee`.
The native presentation is a Claw OS GPL-3.0-only addition to its COSMIC
applets fork. That fork originated at `pop-os/cosmic-applets` commit
`89a149034d06`; its unmodified GPL license is preserved in
[`native/LICENSE`](native/LICENSE), along with the source SPDX notices.

The executable remains hosted by the OS `cosmic-applets` dispatcher. This
repository owns the complete Calendar UI library, localization, desktop entry,
icon and native development build. The OS supplies a typed agenda callback
backed by its shared, policy-gated read-only Calendar provider. Neither this
library nor the Widget Rail calls another App.

Development links the shared Claw OS toolkit (including its vendored iced
tree) from the immutable [`platform.lock.json`](../../platform.lock.json).
Its source licenses and origin notices remain in that dependency. The
[`../../tools/native-patches.toml`](../../tools/native-patches.toml) mapping preserves the original
desktop workspace's toolkit patches; native OS builds apply the same patches
from their own workspace. No toolkit or OS authority implementation is copied.
