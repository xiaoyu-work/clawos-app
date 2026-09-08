# cosmic-screenshot

Utility for capturing screenshots via XDG Desktop Portal

## Claw OS MCP service

The App Host is the only MCP activation path: it starts
`/usr/bin/cosmic-screenshot` with `COS_MCP_SERVER=1`. Tool metadata and
capability needs are authoritative in
`../../apps/cosmic-screenshot/app.json`, staged beside the generated binary
sources for development. See the [Capture product](../../README.md).

The default native interactive portal UI, localization and notifications remain
unchanged. Non-interactive CLI/MCP uses the OS capture service; its internal
`--portal-capture-stdout` mode is the fixed native client of that service,
not an App dispatcher. Installed paths and portal configuration do not move.
Direct human CLI use preserves its connected stderr terminal for the existing
OS bootstrap. Unattended/headless calls require an authenticated OS session.
