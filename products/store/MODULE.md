# Store Product

Own the `pkg` App's thirteen existing CLI operations and matching MCP adapter,
and the complete native `cosmic-store` fork, including Flatpak/PackageKit UI,
translations, assets, original Cargo graph and `flathub-stats` workspace member.

| Path | Responsibility |
| --- | --- |
| `apps/pkg/app.json` | CLI/MCP arguments and existing package/observation capabilities |
| `apps/pkg/main.py` | Read-only apt/dpkg queries and `cos __package` mutation requests |
| `apps/pkg/server.py` | Runtime adapter from manifest operations to SDK MCP |
| `apps/pkg/test_main.py` | Catalog parsing, validation, scoped broker requests and all MCP operation routes |
| `package.json` | Product-owned staging and test inputs |
| `apps/cosmic-store/app.json` | Unchanged four-tool native descriptor and independent grants |
| `native/cosmic-store/src/mcp.rs` | Three catalog queries and fixed Store activation |
| `native/cosmic-store/src/argparse.rs`, `native/cosmic-store/test/unit/argparse.rs` | Native search/helper arguments, bounded Host GUI selector adaptation and parser regressions |
| `native/cosmic-store/src/product.rs`, `product_bridge.py` | Embedded canonical catalog functions; OS policy/snapshot and desktop adapters |
| `native/test_process.py` | Real binary/resource installation and authenticated synthetic stdio fixture |

Preserve the installed `pkg` identity and existing permissions. The OS package
provider now accepts any client with the existing Critical `sys.package` scope
and matching authenticated owner/session; it does not require a `pkg` name.
It still serializes transactions and records mutation/rollback state. Package
effects are system-wide, and this grants neither native Store nor any other
App new default authority. No installed package database, apt configuration or
OS provider code moves into this repository. Product code never invokes another
App, and the GUI must not gain authority by forwarding through `pkg`.

```bash
python3 tools/test.py store
python3 tools/stage.py store --root build/store-stage
python3 tools/native_build.py store test
python3 tools/native_build.py store build
python3 products/store/native/test_process.py
```

Tests mock package queries and mutations; they do not install or remove software.
Native MCP embeds `apps/pkg/main.py` at compilation but invokes only its three
catalog functions, never the App entrypoint or transaction functions. Isolated
system Python imports installed OS SDK/runtime and App-owned common support
from `/usr/lib/cos/python`. The worker's
authenticated session stays intact; call metadata does not grant pkg authority.
Human-only Flatpak data cleanup checks `fs.delete` and snapshots before removal;
ref-file reads check `fs.read`. Both adapters reject MCP use. New Window and
`store.open` use a fixed broker target under `proc.spawn:cosmic-store`.
The existing interactive PackageKit/Flatpak confirmation and provider policies
remain unchanged. UI catalog/backend consolidation, installed-data migration,
full-image integration and interactive/visual acceptance are separate work.

The native payload binds GUI and MCP to the real `bin/cosmic-store`, preserving
resources and licenses. Its compatibility command enters the existing common
Host rather than invoking the relocated ELF directly. The App-owned
`claw-app-gui-argv` library removes one exact argv[1] `--gui` only in SDK GUI mode,
after the existing MCP dispatch. Search/URI/codec strings and helper option
values retain their original boundaries; `-- --gui` remains a positional value.
Help still exits successfully, and the unconfigured `--version` still errors.
This parsing adaptation does not enable resource/provider integration. See
[native payloads](../../docs/native-payloads.md).
