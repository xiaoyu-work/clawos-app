# Application Architecture

`clawos-app` owns independently developed application products. `claw-os`
owns the system Agent, privileged broker, runtime authority, SDK and OS image.

```text
Product UI ----+
              +--> product business implementation --> versioned OS SDK/runtime
Product MCP --+                                             |
                                                       clawd / AI gate
```

Applications do not call one another. One product can have multiple entry
points without duplicating its account state or inheriting a union of grants.

| Surface | Owner |
| --- | --- |
| `products/mail/` | Thunderbird source, Mail AI, legacy email and restricted delivery, extension UI and product packaging |
| `products/calendar/` | Local events, Google/Outlook integration and Calendar MCP |
| `products/files/` | Filesystem MCP operations, metadata, bounded IO and owner-scoped Recoll document search |
| `products/browser/` | Explicit-provider web/image search and its MCP contract |
| `tools/stage.py` | Deterministic assembly of product-owned installed assets |
| `platform.lock.json`, `tools/platform_dependency.py` | Immutable development SDK/runtime dependency, not a second OS implementation |
| `tools/test.py` | Product-scoped tests using the locked runtime |
| `claw-os` | Native authority launcher, package signing, installation, core services and system integration |

OS builds pin a commit of this repository and invoke the product asset builder.
The resulting assets enter the existing signed OS package; installed paths and
App provenance checks do not change. No installed system downloads a mutable
Git branch or silently substitutes an unverified App.

Mail preserves `mail-ai` and its six AI operations, plus the existing `email`
SMTP/Gmail/Outlook implementation. Native Thunderbird source is also owned
here, along with the restricted `gateway-email` delivery adapter. These source moves do not merge
legacy identities or account state; completing that product cutover requires
explicit account, consent and installation changes.

SDK/runtime development dependencies are fetched by immutable commit into
ignored build storage. Only those library source directories are checked out;
product code does not import operating-system implementation files. Published
runtime packages can replace this source dependency without changing the
product interface. The legacy email transport also uses the pinned
`apps/_shared` package and the sibling `canonical_argv.py` shared module
(included by the sparse checkout's parent directory). No other App's
implementation is checked out. OS package assembly already owns these
installed libraries. Delivery imports the distinct `gateway._shared` namespace
from its pinned shared library, rather than colliding with email's `_shared`.
Staging preserves nested App paths; joining their components with `-` must
produce the manifest ID, matching OS discovery.

Each product's `package.json` selects its installed Apps and additional tests.
The test runner includes each declared App's `test_main.py`, then only the
explicit extra tests; it never recursively collects a vendored source tree.
Calendar's event database and provider authority are unchanged by relocation.
OS integration tests consume the pinned product source to retain coverage of
real Calendar code crossing the broker and sandbox boundaries.
