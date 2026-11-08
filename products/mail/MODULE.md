# Mail Product

## Responsibility

Own Mail's native Thunderbird source, shared AI business operations, extension
UI and product asset assembly. The OS owns privileged launch, App sessions,
model policy and signed installation.

| Path | Responsibility |
| --- | --- |
| `comm/` | Full Thunderbird source; native account, message and compose engine |
| `apps/mail-ai/` | Existing six shared AI operations and manifest |
| `apps/email/` | Thunderbird-backed Agent operations, account-scoped needs, stable objects, arrival cursors and submission receipts |
| `apps/gateway/email/` | Restricted outbound SMTP delivery; keeps the nested installed path and `gateway-email` identity |
| `extension/` | AI UI plus native mailbox business operations using Thunderbird's existing account/message APIs |
| `build.py`, `mozconfig`, `upstream.json` | Matched native source build |
| `build-extension.py`, `package.json` | Deterministic XPI and installed asset ownership |
| `PROVENANCE.md` | Upstream revisions, licenses and trademark obligations |

The native product build is independent of the OS Rust workspace. Keep
provider credentials and authorization in the OS; importing source does not
grant access to a user's profile. Installed `mail-ai`, `email` and
`gateway-email` identities and paths remain separate. The Email backend cutover
does not merge them or move credentials/account data. Its newly declared mail
permissions require the normal owner authorization; old provider grants are
not converted into mailbox or sender authority.

## Activity message objects

`email` declares `thunderbird-message` and `thunderbird-draft` object types.
Their IDs encode the profile-qualified account, native folder and RFC Message-ID,
not Thunderbird's numeric IDs, which change on restart or movement.
`native_message` and `native_draft` resolve through the ordinary mailbox client.
Their wildcard declarations inherit already bounded mailbox rights; the OS
checks the exact account encoded in the ID. They do not grant all-account access.
Read/search/list results include canonical `app://email/TYPE?id=...` references.
References do not fetch data, grant access or merge accounts. Moved, missing
or ambiguous messages fail explicitly. Old provider object types/arguments
are retired, not aliased to unrelated Thunderbird messages.

```bash
cos app email read --account ACCOUNT_ID --id MESSAGE_REFERENCE_ID
cos activity attach-object ACTIVITY_ID --label "Source email" \
  --app email --type thunderbird-message --object-id MESSAGE_REFERENCE_ID
```

## Existing transport and packaging

`sync` reads the extension's bounded native inbox-arrival journal without a
model request. The first pass records a non-replaying baseline; subsequent
passes publish `message.received` references before advancing the App-private
account cursor. Expired history requires explicit `--reset`; corrupt state
is not repaired or silently replaced. The old provider continuation files
remain untouched. An OS cron can poll independently of Agent execution;
authorized Activity triggers still consume `app:email` events.
Mail mutations publish reported events through the same SDK namespace.
Event failures preserve the original operation result and never repeat its
external effect. Exact `ipc.publish:app:email` needs are disclosed separately.

`draft_save` saves a real draft through Thunderbird's background message API.
Replacing a draft additionally requires its explicit `source-account` and
separate read/draft rights there. The sender's configured Drafts folder can
belong to another mailbox; returned references identify that actual mailbox.
`native_draft` exposes To/Cc/Bcc, text/HTML and attachment byte fingerprints.
`draft_send` requires the complete current review, explicit confirmation,
mailbox read/draft rights and independent `sender-account` send authority.
The bytes and recipients sent come from the captured reviewed snapshot.
Only an unchanged source draft is removed after successful save/send;
concurrent edits or cleanup failures retain it and are reported explicitly.
Confirmation is neither an OS permission grant nor delivery proof.
The existing `email.draft` remains an AI text helper and never saves or sends.

Outbound `send`, `draft_save` and `draft_send` optionally accept a canonical
UUID `request-id`. The owned `mail-requests` partition durably records the
canonical operation/argument fingerprint before submission and the result
afterward. Identical retries return the retained result; different arguments,
corruption and interrupted in-flight requests never resubmit. Read/write
authority for this store is conditional on supplying the flag. Without it,
the operation has no retained request receipt. This is an App request receipt, not provider
exactly-once delivery or an OS-confirmed effect. Activity workflows should
retain one request ID per reviewed outward action.

`attachment_download` takes an explicit mailbox account, stable message ID,
native MIME-part ID and canonical output path, bounded to 16 MiB. Output
parents must exist; private atomic creation never overwrites an existing
entry. Failed durability after creation is reported as indeterminate.
Attachment filenames never select a destination. `attachment-file` references
resolve through `attachment_file` with only exact metadata authority, while
downloads require `mail.read` plus exact `fs.write`. The OS persists bytes
through its existing pinned non-overwriting filesystem target and task-bound
snapshot path. Attachment bytes do not cross the Python SDK response limit.

Email uses the published SDK's explicit-binary/cancellable kernel transport
for `cos __mail request --request-stdin`. The ordinary Host supplies the real
session. `clawd` validates closed requests, account grants and owner identity;
no caller can choose a provider socket, UID, profile path or executable.
When needed it starts fixed Thunderbird through the owner's service manager,
without the Agent UI or model loop. Installed session/display prerequisites
still apply; unavailable services are explicit errors.
The OS-owned Native Messaging multiplexer admits only root broker mailbox
requests. AI App stdout can return only correlated AI responses, never mailbox
commands. The `mail-ai` host's standing AI/memory ceiling stays unchanged.
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
Protocol tests stage their own source/bootstrap fixture and a fully verified
platform archive selected by the developer test command. The fixture's synthetic
pin is private test data, never a production pin or runtime override; the actual
Native Host continues to exercise its unchanged pinned-source bootstrap.

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
