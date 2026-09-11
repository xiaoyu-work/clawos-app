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
Email's SMTP `send` operation and `email.send` MCP tool require an explicit
`host:port`, such as `mail.example.com:587` or `mail.example.com:465`. That
same argument supplies the manifest's `net.dial` scope, the policy check and
the actual connection. Bare hosts are rejected before policy or credential
access: the worker's exact-endpoint policy otherwise selects port 443, which
is not an SMTP default. `SMTP_PORT` no longer changes Email's destination.
Use `--host server:587` for STARTTLS or `--host server:465` for implicit TLS;
custom explicit ports retain their existing TLS behavior. SMTP credentials,
sender configuration, Gmail/Outlook and the separate gateway configuration
are unchanged. No wildcard grant or sandbox networking exception is added.
The Email process fixture uses OpenSSL, public MCP and a private Unix egress
peer to exercise real STARTTLS/implicit TLS and endpoint refusal. Its policy
responses and messages are synthetic; it sends no real mail and grants no
production authority.
Email's `_shared` dependency is an App-owned common library under
[`shared/python`](../../shared/MODULE.md), not another App or an OS export.
The delivery adapter uses the separately named `gateway._shared` library
from the same common runtime and requires the OS policy/SMTP runtime;
missing runtime cannot enable a direct SMTP fallback. Nested package paths
must continue to derive the same App ID.
Source-checkout Native Messaging resolves named SDK/runtime exports from the
verified platform artifact cache, never a Git directory or sibling OS checkout.
Prepare the pinned artifact explicitly with `tools/platform_dependency.py`;
the isolated native host never downloads build dependencies at runtime and
disables bytecode when importing from that cache. Installed execution retains
the fixed `/usr/lib/cos/python` root and existing OS authority launcher.

That current launcher is a remaining integration exception, not a privilege
Mail should inherit: OS `TrustedNativeHost` admission is still tied to
`mail-ai`, fixed paths and a Thunderbird parent, with a recorded sandbox
exemption. Replacing it belongs to the generic App Host contract and must retain
authenticated ownership/session/audit binding, provenance, capability checks
and equivalent sandbox protections. Do not delete those checks or treat the
source-bootstrap/protocol tests as proof of a completed unified integration.

From the repository root, use `python3 tools/test.py mail`. For native tests,
build first and use `python3 products/mail/build.py test comm/path/to/test.js`.
Contract fixtures do not replace native engine, GUI or package-upgrade tests.
