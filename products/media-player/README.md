# Media Player

The complete native `cosmic-player` product: the original GStreamer video/audio
UI, navigation, repeat/seek/volume/subtitle controls, thumbnailer, portal
integration, 72 locales, resources and seven MCP tools.

UI and MCP operate the same live native playback session. MCP calls the
versioned OS `system.media-player.control` service using the installed
`/usr/local/bin/cos`, not another App or a direct session bus. Status requires
`desktop.media.observe:cosmic-player`; the six controls require
`desktop.media.control:cosmic-player`. Neither grant implies the other.
Both require explicit consent and can be revoked through Settings.

The OS authenticates the owner, installed native executable, PID and unique
MPRIS connection. No native Player, multiple instances, owner mismatch or
spoofed endpoints produce explicit errors; another player's state is never
used. MCP does not launch a window or open media. A running native playback
session is required; there is no synthetic headless playback cache.
Normal MPRIS clients keep working with
`org.mpris.MediaPlayer2.com.clawos.Player.pid<PID>`.
Stop pauses playback and resets seekable tracks without fabricating position
after a failed seek. Empty and ended tracks report Stopped rather than Playing.

The standalone original renderer/toolkit/video dependency graph and lock are
preserved. Only allowlisted immutable SDK/runtime dependencies come from
`platform.lock.json`. Installed identity, resources, user files and
configuration paths are unchanged. See [MODULE.md](MODULE.md) for commands
and [PROVENANCE.md](PROVENANCE.md) for corresponding-source provenance.

Tests use synthetic state and private buses only. Native builds and headless
fixtures do not claim interactive Wayland, real audio/video or full-image
acceptance. Cancellation prevents undispatched work; an already accepted
native playback command is not a reversible transaction.
