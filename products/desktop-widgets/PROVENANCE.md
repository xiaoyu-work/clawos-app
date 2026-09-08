# Desktop Widgets provenance

The `widget-rail` manifest/launcher and full `claw-applet-widget-rail` UI,
localization, desktop entry and UI tests were moved from Claw OS commit
`c0198e5f5380ff05c65871bf0cfd4c225027194f`.
The native code is a GPL-3.0-only Claw OS addition to the COSMIC applets fork,
originally based on `pop-os/cosmic-applets` commit `89a149034d06`.
The original GPL license is retained verbatim in [native/LICENSE](native/LICENSE)
and all source SPDX notices are preserved.

Policy, Calendar access, read-only task collection, telemetry collection and
their provider tests remain in the OS shared service library. Typed host
callbacks replace imports of OS implementation and the Agent Activity App.
The original unused standalone main is superseded by the existing OS host.
No grants, installed paths or live user state change.

The native runner uses only the immutable shared toolkit from
[platform.lock.json](../../platform.lock.json), preserving the existing fork
and its licenses; see [tools/native_build.py](../../tools/native_build.py).
