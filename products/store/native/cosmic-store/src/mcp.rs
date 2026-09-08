//! MCP tool surface for `cosmic-store`.
//!
//! Launched with `COS_MCP_SERVER=1`, the binary becomes a stdio MCP
//! server instead of opening the store GUI. Queries share Store's compiled-in
//! catalog library and retain this App's authenticated observation grants.
//!
//! The authoritative tool catalog and capability contract live in
//! `apps/cosmic-store/app.json`.
//!
//! Install/remove are intentionally **not** exposed: those are
//! impactful operations retain the separate pkg identity and OS transaction
//! approval, audit and rollback flow. The native query surface has no package
//! transaction authority.

use std::sync::Arc;

use async_trait::async_trait;
use claw_os_sdk::mcp::{App, CallContext, Tool, ToolResult};
use serde_json::{json, Value};

async fn query(operation: &'static str, arguments: Value) -> Result<Value, String> {
    tokio::task::spawn_blocking(move || crate::product::query(operation, arguments))
        .await.map_err(|error| error.to_string())?
        .map_err(|error| error.to_string())
}

// ---------------------------------------------------------------------------
// store.search
// ---------------------------------------------------------------------------

struct SearchTool;

#[async_trait]
impl Tool for SearchTool {
    fn name(&self) -> &'static str {
        "store.search"
    }
    async fn handle(&self, input: Value, context: CallContext) -> ToolResult {
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        let query = match input.get("query").and_then(|v| v.as_str()) {
            Some(s) if !s.trim().is_empty() && !s.contains('\0') => s.to_string(),
            _ => return ToolResult::error("query must be nonempty text without NUL"),
        };
        let limit = match input.get("limit") {
            None => 25,
            Some(value) => match value.as_i64() {
                Some(limit) => limit.clamp(1, 100),
                None => return ToolResult::error("limit must be an integer"),
            },
        };
        let result = self::query("search", json!({"query": query, "limit": limit})).await;
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        match result {
            Ok(v) => ToolResult::text(v.to_string()),
            Err(e) => ToolResult::error(format!("store.search: {e}")),
        }
    }
}

// ---------------------------------------------------------------------------
// store.installed
// ---------------------------------------------------------------------------

struct InstalledTool;

#[async_trait]
impl Tool for InstalledTool {
    fn name(&self) -> &'static str {
        "store.installed"
    }
    async fn handle(&self, _input: Value, context: CallContext) -> ToolResult {
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        let result = query("installed", json!({})).await;
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        match result {
            Ok(v) => ToolResult::text(v.to_string()),
            Err(e) => ToolResult::error(format!("store.installed: {e}")),
        }
    }
}

// ---------------------------------------------------------------------------
// store.show
// ---------------------------------------------------------------------------

struct ShowTool;

#[async_trait]
impl Tool for ShowTool {
    fn name(&self) -> &'static str {
        "store.show"
    }
    async fn handle(&self, input: Value, context: CallContext) -> ToolResult {
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        let name = match input.get("name").and_then(|v| v.as_str()) {
            Some(s) if crate::product::valid_package_name(s) => s.to_string(),
            _ => return ToolResult::error("invalid package name"),
        };
        let result = query("show", json!({"name": name})).await;
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        match result {
            Ok(v) => ToolResult::text(v.to_string()),
            Err(e) => ToolResult::error(format!("store.show: {e}")),
        }
    }
}

// ---------------------------------------------------------------------------
// store.open — launch cosmic-store, optionally deep-linked
// ---------------------------------------------------------------------------

struct OpenTool;

#[async_trait]
impl Tool for OpenTool {
    fn name(&self) -> &'static str {
        "store.open"
    }
    async fn handle(&self, input: Value, context: CallContext) -> ToolResult {
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        let name = match input.get("name") {
            None => None,
            Some(Value::String(name)) if crate::product::valid_package_name(name) => Some(name.clone()),
            _ => return ToolResult::error("invalid package name"),
        };
        let res = tokio::task::spawn_blocking(move || {
            crate::product::open(name.as_deref())
        })
        .await;
        match res {
            Ok(Ok(_)) => ToolResult::text(json!({"opened": true}).to_string()),
            Ok(Err(e)) => ToolResult::error(format!("store.open: {e}")),
            Err(e) => ToolResult::error(format!("store.open join: {e}")),
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
        app.bind(Arc::new(SearchTool))?;
        app.bind(Arc::new(InstalledTool))?;
        app.bind(Arc::new(ShowTool))?;
        app.bind(Arc::new(OpenTool))?;
        app.serve_stdio().await
    })
    .map_err(|error| anyhow::anyhow!("cosmic-store MCP server exited: {error}"))
}
