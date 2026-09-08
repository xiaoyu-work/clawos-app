# Terminal

The `exec` App provides command execution, script invocation, executable
lookup and background process start/stop/list operations. It keeps the
existing CLI and MCP adapter, bounded output capture and process registry.

Process permissions and sandbox enforcement remain in Claw OS. This source
move does not rename the App, change grants or migrate user data. Native
Terminal UI and shared session integration remain separate pending work.

See [MODULE.md](MODULE.md) for implementation boundaries and commands.
