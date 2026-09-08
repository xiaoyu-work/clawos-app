//! MCP tool surface for `cosmic-settings`.
//!
//! Launched with `COS_MCP_SERVER=1`, the binary becomes a stdio MCP
//! server instead of opening the settings GUI. The authoritative tool
//! descriptions and argument schemas live in `apps/cosmic-settings/app.json`.

use std::sync::Arc;

use async_trait::async_trait;
use claw_os_sdk::mcp::{App, CallContext, Tool, ToolResult};
use serde_json::{json, Value};

/// The full list of page-commands this build exposes. Keep in sync
/// with `PageCommands` in `main.rs` — keyed by the CLI subcommand
/// the user would type (`cosmic-settings <id>`), with a
/// human-readable label and a one-line description for the agent.
///
/// We intentionally do NOT mirror cargo `cfg(feature = …)` here: the
/// MCP server is informational, and the worst case if a feature is
/// off is `settings.open` failing with a clap parse error — which we
/// surface verbatim.
const PAGES: &[(&str, &str, &str)] = &[
    (
        "accessibility",
        "Accessibility",
        "Magnifier, screen reader, contrast.",
    ),
    ("about", "About", "OS version, hardware info, hostname."),
    ("agent", "Agent", "Default LLM provider, memory, approvals."),
    (
        "appearance",
        "Appearance",
        "Light/dark mode, accent colour, theme import/export.",
    ),
    ("applications", "Applications", "Verified Apps, effective brokered permissions, requests and revocation."),
    (
        "bluetooth",
        "Bluetooth",
        "Pair, unpair, manage Bluetooth devices.",
    ),
    ("date-time", "Date & Time", "Timezone, clock format, NTP."),
    (
        "default-apps",
        "Default Apps",
        "Default browser / mail / image viewer / ...",
    ),
    (
        "desktop",
        "Desktop",
        "Wallpaper-less desktop, hot corners, animations.",
    ),
    (
        "displays",
        "Displays",
        "Resolution, refresh rate, scaling, night light.",
    ),
    ("dock", "Dock", "Position, autohide, size."),
    ("input", "Input", "Keyboard, mouse, touchpad master switch."),
    ("keyboard", "Keyboard", "Layouts, repeat rate, shortcuts."),
    (
        "legacy-applications",
        "Legacy Applications",
        "X11 application compatibility.",
    ),
    (
        "mouse",
        "Mouse",
        "Pointer speed, acceleration, scroll direction.",
    ),
    ("network", "Network", "Connections overview."),
    ("panel", "Panel", "Top bar size, position, applets."),
    (
        "power",
        "Power",
        "Battery, screen timeout, suspend behaviour.",
    ),
    (
        "region-language",
        "Region & Language",
        "Locale, formats, input methods.",
    ),
    (
        "sound",
        "Sound",
        "Output device, input device, volume profiles.",
    ),
    ("startup-apps", "Startup Apps", "What launches at login."),
    (
        "system",
        "System & Accounts",
        "User accounts, password, root.",
    ),
    ("time", "Time & Language", "Locale + clock combined."),
    (
        "touchpad",
        "Touchpad",
        "Tap to click, gestures, palm rejection.",
    ),
    ("users", "Users", "Add / remove / edit local users."),
    ("vpn", "VPN", "VPN profiles."),
    (
        "wallpaper",
        "Wallpaper",
        "Pick wallpaper, slideshow rotation.",
    ),
    (
        "window-management",
        "Window Management",
        "Tiling, focus follows mouse.",
    ),
    ("wired", "Wired", "Ethernet connection details."),
    ("wireless", "Wi-Fi", "Wi-Fi networks, security."),
    ("workspaces", "Workspaces", "Workspace policy + count."),
];

// ---------------------------------------------------------------------------
// settings.list_pages
// ---------------------------------------------------------------------------

struct ListPagesTool;

#[async_trait]
impl Tool for ListPagesTool {
    fn name(&self) -> &'static str {
        "settings.list_pages"
    }
    async fn handle(&self, _input: Value, context: CallContext) -> ToolResult {
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        let pages: Vec<Value> = PAGES
            .iter()
            .map(|(id, label, hint)| json!({ "id": id, "label": label, "hint": hint }))
            .collect();
        ToolResult::text(json!({ "pages": pages }).to_string())
    }
}

// ---------------------------------------------------------------------------
// settings.search
// ---------------------------------------------------------------------------

struct SearchTool;

#[async_trait]
impl Tool for SearchTool {
    fn name(&self) -> &'static str {
        "settings.search"
    }
    async fn handle(&self, input: Value, context: CallContext) -> ToolResult {
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        let query = match input.get("query").and_then(|v| v.as_str()) {
            Some(q) => q.to_lowercase(),
            None => return ToolResult::error("missing query"),
        };
        let limit = input
            .get("limit")
            .and_then(|v| v.as_u64())
            .unwrap_or(5)
            .clamp(1, 20) as usize;
        let mut hits: Vec<Value> = PAGES
            .iter()
            .filter_map(|(id, label, hint)| {
                let hay = format!("{} {} {}", id, label.to_lowercase(), hint.to_lowercase());
                if hay.contains(&query) {
                    Some(json!({ "id": id, "label": label, "hint": hint }))
                } else {
                    None
                }
            })
            .collect();
        hits.truncate(limit);
        ToolResult::text(json!({ "hits": hits }).to_string())
    }
}

// ---------------------------------------------------------------------------
// settings.open
// ---------------------------------------------------------------------------

struct OpenTool;

#[async_trait]
impl Tool for OpenTool {
    fn name(&self) -> &'static str {
        "settings.open"
    }
    async fn handle(&self, input: Value, context: CallContext) -> ToolResult {
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        let page = match input.get("page") {
            None => None,
            Some(Value::String(page)) if valid_page(page) => {
                Some(page.clone())
            }
            _ => return ToolResult::error("unknown Settings page"),
        };
        let res = tokio::task::spawn_blocking(move || open(page.as_deref())).await;
        match res {
            Ok(Ok(_)) => ToolResult::text(json!({"opened": true}).to_string()),
            Ok(Err(e)) => ToolResult::error(format!("settings.open: {e}")),
            Err(e) => ToolResult::error(format!("settings.open join: {e}")),
        }
    }
}

fn open(page: Option<&str>) -> Result<(), cos_runtime::BridgeError> {
    let mut args = vec![
        "__desktop".to_string(), "launch".into(), "--app-id".into(),
        "com.clawos.Settings".into(),
    ];
    if let Some(page) = page {
        args.extend(["--uri".into(), format!("settings://{page}")]);
    }
    let value = claw_os_sdk::cos_call_json_with_binary(
        "/usr/local/bin/cos", "desktop", "launch", args,
    )?;
    if value["launched"] != true || value["app_id"] != "com.clawos.Settings"
        || value["launcher"] != "/usr/bin/cosmic-settings"
    {
        return Err(cos_runtime::BridgeError::Decode {
            app: "desktop".into(), verb: "launch".into(),
            message: "provider did not confirm native Settings launch".into(),
        });
    }
    Ok(())
}

fn valid_page(page: &str) -> bool {
    use clap::CommandFactory;
    crate::Args::command().get_subcommands().any(|command| command.get_name() == page)
}

struct PermissionsTool {
    name: &'static str,
    action: &'static str,
}

#[async_trait]
impl Tool for PermissionsTool {
    fn name(&self) -> &'static str { self.name }

    async fn handle(&self, input: Value, context: CallContext) -> ToolResult {
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        let mut request = input;
        let Some(object) = request.as_object_mut() else {
            return ToolResult::error("permission arguments must be an object");
        };
        if object.keys().any(|key| !matches!(key.as_str(), "app_id" | "permission_id" | "reason")) {
            return ToolResult::error("unsupported permission argument; owner/session/approval cannot be supplied");
        }
        object.insert("action".into(), json!(self.action));
        let result = crate::permissions::call(request).await;
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(format!("{error}; an in-flight request may have completed, refresh its status"));
        }
        match result {
            Ok(value) => ToolResult::structured_with_text(value.clone(), value.to_string())
                .unwrap_or_else(|error| ToolResult::error(error.to_string())),
            Err(error) => ToolResult::error(error),
        }
    }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

pub fn run() -> anyhow::Result<()> {
    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?;
    rt.block_on(async {
        let mut app = App::from_environment()?;
        app.bind(Arc::new(ListPagesTool))?;
        app.bind(Arc::new(SearchTool))?;
        app.bind(Arc::new(OpenTool))?;
        for (name, action) in [
            ("settings.permissions_list", "list"),
            ("settings.permissions_show", "show"),
            ("settings.permissions_request", "request"),
            ("settings.permissions_revoke", "revoke"),
        ] {
            app.bind(Arc::new(PermissionsTool { name, action }))?;
        }
        app.serve_stdio().await
    })
    .map_err(|error| anyhow::anyhow!("cosmic-settings MCP server exited: {error}"))
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/mcp.rs"));
}
