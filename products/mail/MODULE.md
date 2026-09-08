# Mail Product

## Responsibility

Own Mail's native Thunderbird source, shared AI business operations, extension
UI and product asset assembly. The OS owns privileged launch, App sessions,
model policy and signed installation.

| Path | Responsibility |
| --- | --- |
| `comm/` | Full Thunderbird source; native account, message and compose engine |
| `apps/mail-ai/` | Existing six shared AI operations and manifest |
| `apps/email/` | Legacy SMTP/Gmail/Outlook operations, preserving provider-specific grants until the native-engine cutover |
| `apps/gateway/email/` | Restricted outbound SMTP delivery; keeps the nested installed path and `gateway-email` identity |
| `extension/` | Thunderbird UI using those operations |
| `build.py`, `mozconfig`, `upstream.json` | Matched native source build |
| `build-extension.py`, `package.json` | Deterministic XPI and installed asset ownership |
| `PROVENANCE.md` | Upstream revisions, licenses and trademark obligations |

The native product build is independent of the OS Rust workspace. Keep
provider credentials and authorization in the OS; importing source does not
grant access to a user's profile. The repository move preserves installed
`mail-ai`, `email` and `gateway-email` identities, paths, grants and protocols.
All legacy identities still await product consolidation.
Email's `_shared` dependency is a pinned shared library, not another App or a
copied credential/HTTP implementation.
The delivery adapter uses the separately named `gateway._shared` library and
requires the OS policy/SMTP runtime; missing runtime cannot enable a direct
SMTP fallback. Nested package paths must continue to derive the same App ID.

From the repository root, use `python3 tools/test.py mail`. For native tests,
build first and use `python3 products/mail/build.py test comm/path/to/test.js`.
Contract fixtures do not replace native engine, GUI or package-upgrade tests.
