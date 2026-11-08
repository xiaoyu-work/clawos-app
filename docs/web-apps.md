# Released Web Apps

Product Web interfaces live under their owning source group's `web/`.
`package.json` explicitly declares `web_ui.source: "web"` and the consuming
App IDs. Capability-client interfaces remain capability clients, not new
products or installed identities.

Canonical staging includes the product interface, bundled App-owned
presentation helpers, and a package-local `web-ui.json` descriptor. These
files are part of the ordinary signed App inventory. A Web interface does
not introduce a manifest privilege flag, merge another App's grants, or
import an OS checkout. Native preparation uses the same UI assembly before
binding its complete source inventory.

The `claw.web-app/v1` browser transport uses an isolated, script-enabled
sandbox without same-origin privilege. The OS Host supplies the owning
App's authenticated tool descriptions and a view-bound message nonce.
Messages may call only that App's declared MCP tools. The Host retains the
Web credential; App frames receive neither it nor another App's identity.
Every call uses the existing owner-scoped App service and ordinary capability,
review, cancellation and audit checks. Normal App operations require no model
request or running Agent task.

The App Store obtains only authenticated release metadata and immutable
payloads from `xiaoyu-work/clawos-app`. Installation uses the OS's protected
human review and verified directory installer. Catalog signatures, package
signatures, digests and freshness checks are complementary; none grants
runtime permissions. A missing release, unsupported resource or dependency
is an explicit failure, never a source-checkout or unconfined fallback.

Source UI completion is not release approval. The existing publication gate,
independent versions, platform pin, installed identities and native resource
acceptance requirements remain unchanged.

Release publication additionally requires an owner-approved published `cos`
provenance tool URL/SHA256, its App publisher key ID, the public
`CLAW_APPS_PROVENANCE_PUBLISHER_JSON` repository variable, and the dedicated
`CLAW_APPS_PROVENANCE_SIGNING_PRIVATE_KEY` secret. The public OS signer signs
the exact tested Debian App directories; the producer does not implement a
second signature algorithm. Its immutable snapshot assets and authenticated
Store index are published together with the existing App release transaction.
Neither workflow configuration nor this source feature authorizes a release
or changes the platform dependency pin.
