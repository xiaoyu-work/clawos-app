# Desktop Widgets Product

Own the complete native Widget Rail presentation of existing Calendar, Agent
task and system telemetry data. This is shell/Agent presentation, not a new
calendar, task executor, telemetry authority or persistent state owner.

| Path | Responsibility |
| --- | --- |
| `apps/widget-rail/` | Unchanged human-only manifest, shell launcher and exact original grants |
| `native/claw-applet-widget-rail/src/app.rs` | Complete Today, AI Tasks, System Health and deterministic Suggestions cards |
| `native/claw-applet-widget-rail/src/provider.rs` | Typed read-only callbacks and presentation records supplied by the OS host |
| `native/claw-applet-widget-rail/i18n/`, `data/` | Original UI/desktop translations and desktop entry |
| `native/claw-applet-widget-rail/test/unit/` | Original rendering/state helpers and provider/update regressions |
| `native/test_build.py` | Complete native staging and independent build contract |
| `native/Cargo.lock`, `../../tools/native_build.py` | Locked native build against the immutable shared toolkit |
| `PROVENANCE.md`, `native/LICENSE` | Preserved origin and GPL terms |

The OS host supplies each independently authorized provider. Calendar retains
`data.db.read:Name(calendar)` and its existing database path; tasks retain
`agent.observe:Name(tasks)` and `cos agent ls`; telemetry retains the original
`sys.observe:Wild`, bounded `cos sys resources` call and policy-gated Linux
fallback. OS-owned sampling deltas remain process-local. No live data is moved.
Agent execution, task mutations and cross-App orchestration remain OS-owned.
The product imports no other App or OS implementation.

Fast sources refresh every five seconds and Calendar every minute, with
independent in-flight guards and original loading/empty/error presentation.
No visual redesign or extra state store is introduced. The unused standalone
main is replaced by the existing linked `cosmic-applets` host.

```bash
python3 tools/test.py desktop-widgets
python3 tools/native_build.py desktop-widgets test
python3 tools/stage.py desktop-widgets --root build/widget-stage
```

The installed identity remains `widget-rail` / `com.clawos.AppletWidgetRail`,
owned by `claw-os-desktop` with the linked shell, under existing signed updates.
Native tests/builds do not replace interactive Wayland or full-image acceptance.
