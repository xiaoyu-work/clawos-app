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
| `products/mail/` | Thunderbird source, Mail AI implementation, extension UI and product packaging |
| `tools/stage.py` | Deterministic assembly of product-owned installed assets |
| `platform.lock.json`, `tools/platform_dependency.py` | Immutable development SDK/runtime dependency, not a second OS implementation |
| `tools/test.py` | Product-scoped tests using the locked runtime |
| `claw-os` | Native authority launcher, package signing, installation, core services and system integration |

OS builds pin a commit of this repository and invoke the product asset builder.
The resulting assets enter the existing signed OS package; installed paths and
App provenance checks do not change. No installed system downloads a mutable
Git branch or silently substitutes an unverified App.

The initial Mail move preserves `mail-ai` and its existing six AI operations.
Native Thunderbird source is also owned here. The separate legacy `email` and
`gateway-email` implementations have not yet moved or merged; completing that
product cutover requires explicit account, consent and installation changes.

SDK/runtime development dependencies are fetched by immutable commit into
ignored build storage. Only those library source directories are checked out;
product code does not import operating-system implementation files. Published
runtime packages can replace this source dependency without changing the
product interface.
