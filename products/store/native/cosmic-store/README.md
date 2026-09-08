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
