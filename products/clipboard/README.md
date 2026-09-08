# Clipboard

`clipboard-manager` exposes status, MIME types, read, file-backed write and
confirmed clear through five MCP tools. Selection read/write permissions and
exact source-file authority remain separate.

Wayland access and content transfer stay in the OS. No clipboard data or
history is copied by this source migration.

`panel-clipboard` UI and its existing CopyQ history backend remain pending.
The panel's history permissions are not merged into selection access.
See [MODULE.md](MODULE.md) for responsibilities and commands.
