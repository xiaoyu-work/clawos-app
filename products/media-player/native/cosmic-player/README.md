# cosmic-player
WIP COSMIC media player

## Claw OS MCP service

The App Host starts `/usr/bin/cosmic-player` with `COS_MCP_SERVER=1`.
This mode uses the fixed OS playback adapter and the authenticated
`cosmic-player` tool catalog. It holds no desktop session bus and never
selects another player. The normal GStreamer/libcosmic UI publishes live
state and accepts the same native playback commands over its own MPRIS
endpoint. See the [product guide](../../README.md) for permissions,
builds and limitations.
