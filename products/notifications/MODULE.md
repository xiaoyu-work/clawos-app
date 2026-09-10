# Notifications Product

| Path | Responsibility |
| --- | --- |
| `apps/cosmic-notifications/app.json` | Two MCP tools, preserved identity/`ui.notify` grant and explicit durable-ID compatibility |
| `apps/notify/` | Complete Python send/list facade, bounded validation, shared SDK client, separate grants and manifest-dispatch/history-preservation tests |
| `test_notify_process.py` | Installed Python MCP in an empty-root/no-bus sandbox, actual SDK wire decoding, explicit errors and cancellation (canned responses only) |
| `native/cosmic-notifications/src/app.rs` | Complete original Layer Shell UI, popup timers, configuration and presentation |
| `native/cosmic-notifications/src/mcp.rs` | Bounded post/close intent via the fixed installed SDK CLI; no session bus |
| `native/cosmic-notifications/src/subscriptions/` | Freedesktop server, sender-bound numeric handles and private human panel interaction |
| `native/cosmic-notifications/cosmic-notifications-config/` | Private product preferences and existing storage schema |
| `native/cosmic-notifications/cosmic-notifications-util/` | Private notification, markup and image presentation implementation |
| `native/cosmic-notifications/src/presentation.rs` | App-owned adaptation to the OS-defined rendering/preferences contract |
| `native/cosmic-notifications/src/presentation/images.rs` | App-owned theme lookup, bounded raster/vector preparation and normalized pixels/masks |
| `native/cosmic-notifications/test/unit/` | Actual MCP validation, UI model/timers and sender ownership |
| `native/cosmic-notifications/examples/notification-presentation-fixture.rs` | Headless use of the real native subscription on an explicit private bus |
| `native/test_process.py` | Original installer, isolated actual native MCP, typed wire intent, cancellation and explicit failures |
| `package.json` | Complete standalone workspace, separately built private packages and installed descriptor |

The config/util libraries remain private App implementation; they are no
longer exported for OS compilation. The OS owns the lightweight versioned
`claw-notification-presentation` contract in the public SDK artifact. The App
converts its existing markup, image and action behavior to bounded records
over the existing private descriptor connection. It retains the legacy
private interface for older hosts. No unrelated renderer is imposed.

The new preference methods map only to the existing `do_not_disturb` key.
They preserve product defaults, reject malformed updates before writes and
leave anchor/count/timeout/theme settings untouched. This remains the existing
additional popup mute, not OS durable DND policy. No preference/data migration,
permission store or installation acknowledgement is introduced. The new
contract has explicit text/image limits and reports projection failure rather
than returning empty success or an App-provided host path.

The image wire accepts only decoded RGBA8 or symbolic alpha masks, at most
512 by 512 and 1 MiB when materialized. Theme names are resolved here rather
than passed through to an OS decoder. Raster input is limited to 1 MiB encoded,
4096 per dimension and 4,194,304 source pixels before pixel decode; output is
downsampled as needed. Decoder allocation limits are additional best-effort
controls, not a hard App memory/CPU quota or a substitute for Host isolation.
SVG input is uncompressed UTF-8 without DTDs, with 4096 XML nodes, bounded
geometry and at most 16 embedded raster images. External file/URI references
and nested encoded SVG are rejected explicitly; approved embedded rasters
are decoded/normalized here before rendering. Symbolic SVGs become alpha
masks, and regular SVGs retain their colors. The panel never decodes these
source formats. Vector snapshots preserve the existing square icon viewport
and non-square SVG cropping instead of stretching the artwork. A genuinely
missing theme icon retains the former no-icon
presentation with a specific warning; corrupt/excessive images are errors.
Resource images are snapshots at projection time; symbolic foreground color
still follows the OS theme and inherited button/icon state at render time.

The authoritative Notification Service, owner/App identity, consent, audit,
SQLite history, retention, DND, channel preferences and delivery leases/retries
remain in `claw-os`. Its existing desktop bridge is the single delivery
consumer; this product never claims that queue, reads the core database, or
duplicates durable state. External freedesktop presentations remain untrusted
and do not gain authority from hints or display labels. Native/local settings
remain unchanged. Legacy `notify` JSON is explicitly preserved in place and
excluded from new service lists, not imported or replayed. New sends/lists use
only the owner's distinct `app:notify` OS producer; native close stays
native-source-only. See [README.md](README.md) for response/state compatibility
and the actual legacy data namespace.

Run on Linux/WSL from the repository root:

```sh
python3 tools/test.py notifications
python3 tools/native_build.py notifications test
python3 tools/native_build.py notifications build
python3 products/notifications/native/test_process.py
```

The process fixture accepts `--binary`, `--source`, and `--cos-binary` for
immutable OS-composed source and the actual CLI. Without the last option it
uses a fixture-only wire CLI and canned broker responses, not an OS provider
copy. Real strict-worker/authority/SQLite/delivery/native-subscription acceptance
is owned by the OS's
`notifications_actual_native_worker_durable_delivery_and_owner_bound_ui` test.
The paired OS Notify fixture additionally signs/stages the real Python App,
checks broker scope/owner isolation and durable restart behavior, and drives
the same native presentation pipeline.
Neither fixture connects to user services, reads user history or sends remote
notifications. Headless coverage is not visual/full-image acceptance.
New native tests also exercise the actual App presentation server with the
public client over a private socket pair, unchanged product preference files,
invalid authority/configuration fields, image snapshots and unavailable channels.
Standard native builds require a declared SDK artifact containing the new
companion crate; local candidate experiments are not production release pins.
