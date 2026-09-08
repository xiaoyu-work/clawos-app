# Cosmic Settings

## Claw OS MCP service

The App Host starts `/usr/bin/cosmic-settings` with `COS_MCP_SERVER=1`.
The informational page tools, fixed Settings launcher and four permission
tools are declared in the [product manifest](../../../apps/cosmic-settings/app.json);
the Rust service only binds handlers. Applications UI and MCP share the same
explicit `/usr/local/bin/cos` SDK client. Only the human UI may invoke the
fixed polkit helper; restoration state and owner/App revocation remain OS-owned.