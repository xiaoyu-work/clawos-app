# Desktop Widgets Product

Own the complete native Widget Rail presentation of existing Calendar, Agent
task and system telemetry data. This is shell/Agent presentation, not a new
calendar, task executor, telemetry authority or persistent state owner.

| Path | Responsibility |
| --- | --- |
| `apps/widget-rail/` | Standalone native launcher, unchanged human-only manifest and exact original grants |
| `native/claw-applet-widget-rail/src/app.rs` | Complete Today, AI Tasks, System Health and deterministic Suggestions cards |
| `native/claw-applet-widget-rail/src/provider.rs` | Existing typed read-only callback seam and presentation records |
| `native/claw-applet-widget-rail/src/main.rs`, `src/service.rs` | Standalone entry and independent public OS SDK clients |
| `native/claw-applet-widget-rail/build.rs`, `justfile` | Product-owned localized desktop generation and binary installation |
| `native/claw-applet-widget-rail/i18n/`, `data/` | Original UI/desktop translations and desktop entry |
| `native/claw-applet-widget-rail/test/unit/` | Original rendering/state helpers and provider/update regressions |
| `native/test_build.py` | Complete native staging and independent build contract |
| `native/Cargo.lock`, `../../tools/native_build.py` | Locked native build against the immutable shared toolkit |
| `PROVENANCE.md`, `native/LICENSE` | Preserved origin and GPL terms |

The fixed OS applet service supplies each independently authorized provider. Calendar retains
`data.db.read:Name(calendar)` and its existing database path; tasks retain
`agent.observe:Name(tasks)` and `cos agent ls`; telemetry retains the original
`sys.observe:Wild`, bounded `cos sys resources` call and policy-gated Linux
fallback. OS-owned sampling deltas remain process-local in a persistent private helper,
never serialized back to the UI as provider state. No live data is moved.
Agent execution, task mutations and cross-App orchestration remain OS-owned.
The product imports no other App or OS implementation.

The Rust UI uses the same verified App manifest, identity/session, capability
and sandbox contract as every App. Its language, UI and package origin select
no special integration tier. The public data service uses resource scopes,
not a Widget Rail identity exemption or native App allowlist entry.

Fast sources refresh every five seconds and Calendar every minute, with
independent in-flight guards and original loading/empty/error presentation.
No visual redesign or extra state store is introduced. The standalone main
uses separate SDK clients so each source keeps its independent refresh/error
state. None calls another App or opens a worker desktop transport.

```bash
python3 tools/test.py desktop-widgets
python3 tools/native_build.py desktop-widgets test
python3 tools/stage.py desktop-widgets --root build/widget-stage
```

The installed identity remains `widget-rail` / `com.clawos.AppletWidgetRail`.
The product's `just install` copies the actual `/usr/bin/claw-applet-widget-rail`
ELF and generated desktop entry. Its independent App package requires
`claw-os-applet-services-v1 (= 1)`, not a linked OS shell; `cosmic-applets` reads
none of its source/assets. The recipe requires an explicit non-root staging
`rootdir`; it installs files, never permissions or installed-system hooks.
Original UI tests remain and the integration test
runs the real binary headlessly. These checks do not replace interactive
Wayland or full-image acceptance.
