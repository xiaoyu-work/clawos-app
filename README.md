# Claw OS Apps

Official application products for [Claw OS](https://github.com/xiaoyu-work/claw-os),
developed separately from the operating system.

Each product owns its UI, business implementation, Agent MCP surface,
manifests, resources, tests and build inputs. System services and authority
remain in Claw OS.

Shared capability clients are explicitly separate from business products:
[`capabilities/document-engine`](capabilities/document-engine/MODULE.md) owns
the legacy `doc` source and consumes Files' declared parsing library. This
brings source ownership to 71/75 original identities in 24 business product
groups plus one shared-capability group (59 Agent, 12 desktop), without
renaming identities, merging grants/state, or migrating `db`, `kv`, `net` or
`summarize`.

| Product | Source | Migration state |
| --- | --- | --- |
| Mail | [products/mail](products/mail/README.md) | Native Thunderbird source, Mail AI/UI, legacy email and restricted delivery have moved; product consolidation remains pending |
| Calendar | [products/calendar](products/calendar/README.md) | Event operations, provider integration and complete native panel UI/build have moved; OS policy and data paths remain unchanged |
| Files | [products/files](products/files/README.md) | Complete native UI/library/companion, filesystem and Recoll MCP, shared document parsing and SDK AI; source moved, identities/data remain separate |
| Browser | [products/browser](products/browser/README.md) | `search`, `web`, `browser-attached`, Native Host and MV3 extension have moved; native browser UI remains pending |
| Terminal | [products/terminal](products/terminal/README.md) | `exec` operations have moved; native UI and shared terminal-session integration remain pending |
| Containers | [products/containers](products/containers/README.md) | `container-manager` CLI/MCP source has moved; backend execution and authority remain OS-owned |
| Backup and Recovery | [products/backup-recovery](products/backup-recovery/README.md) | `backup-center` and `system-snapshot` have moved with separate permissions; execution, credentials and snapshot state remain OS-owned |
| Store | [products/store](products/store/README.md) | Complete native Store UI/MCP/resources and shared pkg catalog source; OS transactions and native grants stay separate; UI/backend data consolidation remains pending |
| Diagnostics | [products/diagnostics](products/diagnostics/README.md) | `hardware-center`, `crash-doctor` and `netdiag` have moved with separate permissions; privileged collection and network probes stay OS-owned |
| Storage | [products/storage](products/storage/README.md) | `storage-manager` has moved; UDisks2 execution and block-device checks stay OS-owned; existing data is unchanged |
| Settings | [products/settings](products/settings/README.md) | Complete native UI/workspace/MCP/resources plus eleven management Apps; twelve identities and provider grants remain independent; visual acceptance and backend consolidation remain separate |
| Security | [products/security](products/security/README.md) | `security-center`, `firewall-manager` and `usb-guard` have moved with separate grants; inspection, nftables/USB execution and durable state remain OS-owned |
| Maintenance | [products/maintenance](products/maintenance/README.md) | `config-editor` and `systemd` have moved with separate exact-path/unit grants; configuration/service execution, state and rollback remain OS-owned |
| Events and Audit | [products/events-audit](products/events-audit/README.md) | `event-center` and legacy `log` have moved; OS event/audit authority stays separate; typed audit-service integration remains pending |
| Launcher | [products/launcher](products/launcher/README.md) | Python `launcher` has moved; native UI/build, legacy forwarding replacement and shared catalog/history integration remain pending |
| Clipboard | [products/clipboard](products/clipboard/README.md) | `clipboard-manager` has moved; Wayland execution stays OS-owned; native panel and CopyQ history integration remain pending |
| Notification Delivery | [products/notification-delivery](products/notification-delivery/README.md) | One-shot `gateway-ntfy`, `gateway-pushover` and `gateway-webhook` have moved; durable notification service and Rust ntfy dispatcher stay OS-owned; service integration remains separate |
| Home Integration | [products/home-integration](products/home-integration/README.md) | `gateway-homeassistant` REST adapter has moved; external server/device state, OS egress and credentials remain separate; no new UI |
| Desktop Widgets | [products/desktop-widgets](products/desktop-widgets/README.md) | Complete native Widget Rail UI/build/resources; independently authorized Calendar/task/telemetry providers remain OS-owned |
| Editor | [products/editor](products/editor/README.md) | Complete native UI, MCP, AI presentation, resources and build; filesystem/snapshot authority and AI providers remain OS-owned |
| Capture | [products/capture](products/capture/README.md) | Complete native portal client, MCP, translations/resources and original build; interactive UI stays in the OS portal, and non-interactive capture uses scoped OS authority |
| Media Player | [products/media-player](products/media-player/README.md) | Complete native video/audio UI, MPRIS/MCP, resources and original build; UI/MCP share live playback under separate owner-bound OS grants |
| Notifications | [products/notifications](products/notifications/README.md) | Complete native Layer Shell UI/crates/build and Python `notify` send/list; shared authoritative OS state/delivery with distinct producer grants; old JSON preserved in place, not imported |

Start with [ARCHITECTURE.md](ARCHITECTURE.md) and [AGENTS.md](AGENTS.md).
Messaging connector sources are grouped under
[products/messaging-channels](products/messaging-channels/README.md), starting
with Discord/Telegram and outbound-only DingTalk/Google Chat/Lark/Matrix/Mattermost/Rocket.Chat/Signal/Slack/SMS/Teams/Webex/WhatsApp/Zulip.
Source relocation does not complete
authenticated inbound admission.

On Linux/WSL, run Mail contracts with `python3 tools/test.py mail`.
Run Calendar contracts with `python3 tools/test.py calendar`, or select both
products in one invocation: `python3 tools/test.py mail calendar`.
Run Doc and its shared Files consumers together with
`python3 tools/test.py files --capability document-engine`; stage only Doc with
`python3 tools/stage.py document-engine --kind capability --root build/doc-stage`.
Native Mail uses `python3 products/mail/build.py build -j 8` after the
preparation described in its README.

The root license covers first-party code imported from Claw OS; vendored
products retain their own licenses and notices. Thunderbird is principally
MPL-2.0. Its name/logo are not licensed for unrestricted reuse.
