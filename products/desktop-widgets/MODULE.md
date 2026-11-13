# Desktop Widgets Product

Own the complete native Widget Rail presentation of existing Calendar, Agent
task and system telemetry data. This is shell/Agent presentation, not a new
calendar, task executor, telemetry authority or persistent state owner.

| Path | Responsibility |
| --- | --- |
| `apps/widget-rail/` | Existing identity, manifest-bound native GUI/MCP and exact original grants |
| `native/claw-applet-widget-rail/src/app.rs` | Complete Today, AI Tasks, System Health and deterministic Suggestions cards |
| `native/claw-applet-widget-rail/src/provider.rs` | Existing typed read-only callback seam and presentation records |
| `native/claw-applet-widget-rail/src/main.rs`, `src/service.rs`, `src/mcp.rs` | MCP-first entry and shared read-only public OS SDK clients |
| `native/claw-applet-widget-rail/build.rs`, `justfile` | Product-owned localized desktop generation and binary installation |
| `native/claw-applet-widget-rail/i18n/`, `data/` | Original UI/desktop translations and desktop entry |
| `native/claw-applet-widget-rail/test/unit/` | Original rendering/state helpers and provider/update regressions |
| `native/test_build.py` | Complete native staging and independent build contract |
| `native/Cargo.lock`, `../../tools/native_build.py` | Locked native build against the immutable shared toolkit |
| `PROVENANCE.md`, `native/LICENSE` | Preserved origin and GPL terms |

The published SDK 0.2.0 generic wire client selects the fixed
`/usr/local/bin/cos` binary for each independently authorized read. Calendar
retains `data.db.read:Name(calendar)` and uses the owner-scoped
`__calendar day <year> <month> <day>` service with the runtime's local day.
Tasks retain `agent.observe:Name(tasks)` and use `cos --wire=1 __observe tasks`;
telemetry requests only `sys.observe:Name(resources)` and uses
`cos --wire=1 __observe resources`. These commands use the existing SessionAction
wire to the generic Root-owned read-only observer. The OS binds the authenticated
owner; task results contain only `id`, `purpose`, `status` and `created_at`,
never leases or task arguments. The ordinary `agent ls` Task-only route is not
an App observation interface.

The client decodes `{tasks: [Task]}` and `{summary: SystemSummary}` directly into
the existing public SDK types. The Root host owns telemetry observation and
sampling; nullable first CPU/network samples remain unavailable until reported,
and subsequent samples and the OS `fallback` flag are preserved unchanged.
There is no fallback to `agent ls` or `sys resources`, no local `/proc` sampler,
copied provider, Desktop-only helper or fabricated telemetry. No live data is moved.
Agent execution, task mutations and cross-App orchestration remain OS-owned.
The product imports no other App or OS implementation.

## Read-only MCP and owning Web cards

The same real `bin/claw-applet-widget-rail` serves the native UI and lazy stdio
MCP. Dispatch precedes GUI initialization and the original direct `--version`
handling; other native arguments retain their ignored behavior.

| Tool | Exact independent need | Result |
| --- | --- | --- |
| `widget-rail.calendar` | `data.db.read:Name(calendar)` | `{events: [CalendarEvent]}` |
| `widget-rail.tasks` | `agent.observe:Name(tasks)` | `{tasks: [Task]}` |
| `widget-rail.system` | `sys.observe:Name(resources)` | `{summary: SystemSummary}` |

Tools accept no arguments and never start/modify tasks or invoke a model.
One card cannot borrow the GUI's grant union or another card's permission.
The coordinated 0.2.1 `desktop.needs` explicitly requests those three reads
and the separate high-risk `ui.panel` capability for native presentation.
Protected owner approval, not widget metadata or read authority, admits the
panel surface. None of the three MCP tools requests or inherits `ui.panel`.
The standalone entry explicitly creates a top-right Layer Shell surface with
no keyboard interactivity and suppresses the toolkit's default XDG window.
Its 360-by-628 presentation preserves the original 620-pixel scrollable cards
and padding. Geometry and panel metadata supply no display authority.
The OS retains owner/session authorization and state. Calls have a 12-second bound;
cancellation/deadlines drop the public SDK CLI future. The Web page renders
real event/task/resource fields with independent loading, denied/unavailable
and empty states, never raw JSON or placeholder live values. Native `Providers`
callbacks use the same clients without requiring MCP or an active AI Agent.

The Rust UI uses the same verified App manifest, identity/session, capability
and sandbox contract as every App. Its language, UI and package origin select
no special integration tier. The public data service uses resource scopes,
not a Widget Rail identity exemption or native App allowlist entry.

Fast sources refresh every five seconds and Calendar every minute in both
presentations, with independent in-flight guards and loading/empty/error
presentation. No native visual redesign or extra state store is introduced.
None calls another App or opens a worker desktop transport.

```bash
python3 tools/test.py desktop-widgets
python3 tools/native_build.py desktop-widgets test
python3 tools/stage.py desktop-widgets --root build/widget-stage
```

The installed identity remains `widget-rail` / `com.clawos.AppletWidgetRail`.
The product's `just install` copies the actual `/usr/bin/claw-applet-widget-rail`
ELF and generated desktop entry. `native_payload` preserves that ELF, resources
and original GPL license inside the package-local App; source staging never
fabricates a runnable binary. Compatibility launchers use the common Host.
Canonical native builds select the shared App build helper for the exact
current Cargo-reported desktop entry; custom target directories and Cargo
output-layout changes do not select a guessed or stale `xdgen` file.
The binary no longer needs `claw-os-applet-provider`; shared release metadata
requires the Agent-provided `claw-os-calendar-read-v1 (= 1)` and
`claw-os-observation-v1 (= 1)` interfaces. `cosmic-applets` reads
none of its source/assets. The recipe requires an explicit non-root staging
`rootdir`; it installs files, never permissions or installed-system hooks.
Original UI tests remain and the integration test
runs the real binary headlessly. Synthetic CLI/MCP fixtures cover the declared
reads and independent denials without real services or accounts. These checks do not replace interactive
Wayland or full-image acceptance.

The separate clean-CI Widget Rail lane at OS source
`6024681b09b1df921c2c5015549051cc7dd3bc55`, using immutable App source
`4aa63d3c9abc765568db88a3ae6dddd4489ce7e3`, verified the original signed
standalone panel, three independent owner-scoped SDK reads and checked
process/cgroup/runtime/window/PAM retirement without a model. Protected
same-instance SHM bytes were inspected directly: the themed header, Calendar
event, empty task state, memory/storage and deterministic suggestions were
readable. CPU/network warm-up retained the OS's unavailable first samples.
This closes that bounded read-only UI/resource gate, not hardware/default-WGPU,
other native surfaces or full release readiness.
