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

## Native GUI arguments

After MCP dispatch, SDK GUI mode removes only one exact argv[1] `--gui` Host
selector before the existing lexer. Media order, file canonicalization and
`--size`/`--thumbnail` values (including values beginning with `--`) are
unchanged. Unknown flags and invalid sizes still warn and continue; help/version
still exit successfully. The lexer does not gain a new `--` end-of-options
state. `test/unit/argparse.rs` tests this boundary without playback or a GUI.
Thumbnail and resource authority are unchanged.
