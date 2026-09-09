# Notifications Product

| Path | Responsibility |
| --- | --- |
| `apps/cosmic-notifications/app.json` | Two MCP tools, preserved identity/`ui.notify` grant and explicit durable-ID compatibility |
| `apps/notify/` | Complete Python send/list facade, bounded validation, shared SDK client, separate grants and manifest-dispatch/history-preservation tests |
| `test_notify_process.py` | Installed Python MCP in an empty-root/no-bus sandbox, actual SDK wire decoding, explicit errors and cancellation (canned responses only) |
| `native/cosmic-notifications/src/app.rs` | Complete original Layer Shell UI, popup timers, configuration and presentation |
| `native/cosmic-notifications/src/mcp.rs` | Bounded post/close intent via the fixed installed SDK CLI; no session bus |
| `native/cosmic-notifications/src/subscriptions/` | Freedesktop server, sender-bound numeric handles and private human panel interaction |
| `native/cosmic-notifications/cosmic-notifications-config/` | Exported shared presentation configuration schema |
| `native/cosmic-notifications/cosmic-notifications-util/` | Exported shared notification, markup and image presentation types |
| `native/cosmic-notifications/test/unit/` | Actual MCP validation, UI model/timers and sender ownership |
| `native/cosmic-notifications/examples/notification-presentation-fixture.rs` | Headless use of the real native subscription on an explicit private bus |
| `native/test_process.py` | Original installer, isolated actual native MCP, typed wire intent, cancellation and explicit failures |
| `package.json` | Complete standalone workspace, separately built packages, public native libraries and installed descriptor |

The config/util libraries are explicitly exported build inputs. The OS links
them from its immutable `build/native-apps/cosmic-notifications/` composition;
this is not an import of another App's handlers. The native binary preserves
its original git libcosmic/panel configuration graph and optional systemd
feature. No unrelated applet renderer is imposed.

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
