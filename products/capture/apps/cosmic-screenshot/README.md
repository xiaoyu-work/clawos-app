# cosmic-screenshot — native Capture MCP

This is the manifest half of [Capture](../../README.md). The complete native
implementation is in `../../native/cosmic-screenshot/` and installs to the
unchanged `/usr/bin/cosmic-screenshot`.

The App Host selects that fixed root-owned vendor binary with `COS_MCP_SERVER=1`.
The SDK validates the manifest/tool/call-context contract. The only MCP tool,
`screenshot.capture`, uses `desktop.capture:screen` and an exact
`fs.write:save_dir` grant. `save_dir` retains its owner-resolved `~/Pictures`
default; `modal` defaults true. Interactive selection and clipboard actions
are human-only, never an MCP output-policy bypass.

The MCP worker holds no desktop transport. It calls the typed OS capture
service, which starts the same product's fixed portal pipe mode in the owner's
session and persists the PNG. The response is `{cancelled, path}`; cancellation
returns a null path. Portal, service, permission and output errors are surfaced.
No Files/Terminal/notification App, borrowed identity, generic command bridge,
live screenshot or state migration is involved.
