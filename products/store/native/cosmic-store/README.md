# cosmic-store
WIP COSMIC Store

## Claw OS MCP service

The App Host starts `/usr/bin/cosmic-store` with `COS_MCP_SERVER=1`.
The product's `apps/cosmic-store/app.json` is the sole authority for the Store MCP tool
catalog and its capability requirements.

Build from the application repository with `python3 tools/native_build.py store build`.
This preserves the standalone workspace and original default features. The native
query adapter embeds the product's canonical catalog source at compile time;
it never invokes another App or receives pkg transaction authority.

## Native GUI arguments

After MCP dispatch, SDK GUI mode removes only one exact argv[1] `--gui` Host
selector before the original Clap parser. Search, URI and GStreamer codec
strings remain single arguments, and helper option values are not rewritten.
`-- --gui` still supplies a positional search value. Direct CLI errors and help
are unchanged; `--version` remains unsupported and exits with status 2.
`test/unit/argparse.rs` covers this parsing boundary without initializing the
GUI, package backends or user configuration.
