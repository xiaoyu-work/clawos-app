# Launcher

The `launcher` App provides list, find, open, recent and is-running MCP tools.
It owns XDG catalog parsing, search and its existing recent-history logic.
Desktop launch execution and user-session authority remain in the OS.

AppID and local-file grants stay exact; the App does not execute desktop
`Exec=` commands directly. This source move copies no installed catalog,
runtime history or desktop session state.

Native `cosmic-launcher` UI/build/resources, its old App forwarding and shared
catalog/history integration are still pending. The Python source move alone
does not complete the native Launcher product.

See [MODULE.md](MODULE.md) for responsibilities and commands.
