# Claw OS Apps

Official application products for [Claw OS](https://github.com/xiaoyu-work/claw-os),
developed separately from the operating system.

Each product owns its UI, business implementation, Agent MCP surface,
manifests, resources, tests and build inputs. System services and authority
remain in Claw OS.

| Product | Source | Migration state |
| --- | --- | --- |
| Mail | [products/mail](products/mail/README.md) | Native Thunderbird source, Mail AI/UI, legacy email and restricted delivery have moved; product consolidation remains pending |
| Calendar | [products/calendar](products/calendar/README.md) | Event operations and provider integration have moved; panel presentation remains pending |
| Files | [products/files](products/files/README.md) | Direct `fs` and Recoll-backed `docs` MCP operations have moved; native UI remains pending |
| Browser | [products/browser](products/browser/README.md) | `search`, `web`, `browser-attached`, Native Host and MV3 extension have moved; native browser UI remains pending |
| Terminal | [products/terminal](products/terminal/README.md) | `exec` operations have moved; native UI and shared terminal-session integration remain pending |
| Containers | [products/containers](products/containers/README.md) | `container-manager` CLI/MCP source has moved; backend execution and authority remain OS-owned |
| Backup and Recovery | [products/backup-recovery](products/backup-recovery/README.md) | `backup-center` has moved; OS execution and credentials remain broker-owned; `system-snapshot` is pending |

Start with [ARCHITECTURE.md](ARCHITECTURE.md) and [AGENTS.md](AGENTS.md).
On Linux/WSL, run Mail contracts with `python3 tools/test.py mail`.
Run Calendar contracts with `python3 tools/test.py calendar`, or select both
products in one invocation: `python3 tools/test.py mail calendar`.
Native Mail uses `python3 products/mail/build.py build -j 8` after the
preparation described in its README.

The root license covers first-party code imported from Claw OS; vendored
products retain their own licenses and notices. Thunderbird is principally
MPL-2.0. Its name/logo are not licensed for unrestricted reuse.
