# Clipboard

`clipboard-manager` exposes status, MIME types, read, file-backed write and
confirmed clear through five MCP tools. Selection read/write permissions and
exact source-file authority remain separate.

Wayland access and content transfer stay in the OS. No clipboard data or
history is copied by this source migration.

`panel-clipboard` keeps the existing native GUI and owns four manifest-bound
MCP tools plus its Web history list/selection/preview and reviewed actions.
The OS brokers every CopyQ operation; the App never executes CopyQ directly.
History read does not grant selection access. Restoring to the live clipboard
separately requires selection-write; existing grants are not widened.
Missing CopyQ/service is explicit, never a fake empty list or local fallback.
Installed GUI acceptance and publication remain separately gated.
See [MODULE.md](MODULE.md) for responsibilities and commands.
