//! Controlled OS package queries and fixed desktop activation.

use std::io::{self, Write};
use std::process::{Command, Stdio};
use std::sync::Mutex;
use serde::Deserialize;
use serde_json::{Value, json};

const BACKEND: &str = include_str!("../catalog_backend.py");
const BRIDGE: &str = include_str!("../product_bridge.py");

pub fn query(operation: &str, arguments: Value) -> io::Result<Value> {
    if matches!(operation, "search" | "installed" | "show" | "catalog" | "updates" | "store" | "refresh"
        | "flatpak-refresh" | "flatpak-catalog" | "flatpak-installed" | "flatpak-updates")
    {
        let invalid = || io::Error::new(io::ErrorKind::InvalidInput, "invalid package query");
        let mut args = vec!["__package_query".to_string(), operation.to_string()];
        if matches!(operation, "flatpak-catalog" | "flatpak-installed" | "flatpak-updates") {
            let scope = arguments["scope"].as_str().filter(|scope| matches!(*scope, "user" | "system"))
                .ok_or_else(invalid)?;
            args.push(scope.to_string());
        }
        match operation {
            "search" => {
                let query = arguments["query"].as_str().ok_or_else(invalid)?;
                let limit = arguments["limit"].as_u64().filter(|limit| (1..=100).contains(limit))
                    .ok_or_else(invalid)?;
                args.extend([query.to_string(), limit.to_string()]);
            }
            "show" => {
                let name = arguments["name"].as_str().filter(|name| valid_package_name(name))
                    .ok_or_else(invalid)?;
                args.push(name.to_string());
            }
            "catalog" | "flatpak-catalog" => {
                if let Some(cursor) = arguments.get("cursor").filter(|value| !value.is_null()) {
                    let cursor = cursor.as_str().filter(|cursor| cursor.len() <= 128)
                        .ok_or_else(invalid)?;
                    args.push(cursor.to_string());
                }
            }
            _ => {}
        }
        // All backend snapshots share one bounded OS route. Queue them here
        // without making a slow source refresh block browsing.
        static SNAPSHOT_QUERY: Mutex<()> = Mutex::new(());
        let _guard = if matches!(operation, "store" | "refresh" | "flatpak-refresh") {
            None
        } else {
            Some(
                SNAPSHOT_QUERY
                    .lock()
                    .map_err(|_| io::Error::other("Store metadata reader is unavailable"))?,
            )
        };
        return claw_os_sdk::cos_call_json("package", "query", args)
            .map_err(|error| io::Error::other(error.to_string()));
    }
    let backend = serde_json::to_string(BACKEND)?;
    let bridge = serde_json::to_string(BRIDGE)?;
    let mut child = Command::new("/usr/bin/python3")
        .args(["-I", "-c", &format!(
            "import sys,os,json,types\n\
             sys.path[:0] = ['/usr/lib/cos/python']\n\
             os.environ['COS_BIN'] = '/usr/local/bin/cos'\n\
             os.environ['CLAW_COS_BIN'] = '/usr/local/bin/cos'\n\
             backend = types.ModuleType('store_catalog')\n\
             backend.__file__ = '/usr/lib/cos/apps/cosmic-store/embedded.py'\n\
             exec(compile({backend}, '<store-catalog>', 'exec'), backend.__dict__)\n\
             exec(compile({bridge}, '<store-bridge>', 'exec'))\n"
        )])
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped())
        .spawn()?;
    let request = serde_json::to_vec(&json!({"operation": operation, "arguments": arguments}))?;
    let input = child.stdin.take().expect("piped input");
    let (output, written) = std::thread::scope(|scope| {
        let writer = scope.spawn(move || {
            let mut input = input;
            input.write_all(&request)
        });
        let output = child.wait_with_output();
        let written = writer.join().unwrap_or_else(|_| Err(io::Error::other("input writer panicked")));
        (output, written)
    });
    let output = output?;
    let value: Value = serde_json::from_slice(&output.stdout).map_err(|error| {
        io::Error::other(format!("Store helper: {error}: {}", String::from_utf8_lossy(&output.stderr)))
    })?;
    if !output.status.success() {
        return Err(io::Error::other(value["error"].as_str().unwrap_or("Store helper failed")));
    }
    written?;
    Ok(value)
}

#[derive(Deserialize)]
struct CatalogItem {
    source: String,
    xml: String,
}

#[derive(Deserialize)]
struct CatalogPage {
    revision: String,
    configured: bool,
    items: Vec<CatalogItem>,
    count: usize,
    total: usize,
    next: Option<String>,
}

pub fn visit_catalog(
    mut visit: impl FnMut(&str, &str) -> Result<(), Box<dyn std::error::Error>>,
) -> Result<bool, Box<dyn std::error::Error>> {
    let mut cursor: Option<String> = None;
    let mut snapshot = None;
    let mut received = 0;
    loop {
        let page: CatalogPage = serde_json::from_value(query("catalog", json!({"cursor": cursor}))?)?;
        let identity = (page.revision, page.configured, page.total);
        if page.count != page.items.len() || page.total > 100_000
            || received + page.count > page.total
            || snapshot.as_ref().is_some_and(|prior| *prior != identity)
            || page.items.is_empty() && page.next.is_some()
        {
            return Err("The OS catalog page does not match its retained revision".into());
        }
        snapshot = Some(identity);
        for item in page.items {
            visit(&item.source, &item.xml)?;
        }
        received += page.count;
        match page.next {
            Some(next) => cursor = Some(next),
            None if received == page.total => return Ok(page.configured),
            None => return Err("The OS catalog snapshot is incomplete".into()),
        }
    }
}

pub(crate) fn claw_app_package(name: &str) -> bool {
    name.starts_with("claw-cap-") || name.starts_with("claw-app-")
        && !name.starts_with("claw-app-python-")
        && name != "claw-app-support" && name != "claw-app-support-v1"
}

pub fn open(name: Option<&str>) -> Result<(), cos_runtime::BridgeError> {
    let mut args = vec![
        "__desktop".to_string(), "launch".into(), "--app-id".into(), "com.clawos.Store".into(),
    ];
    if let Some(name) = name {
        if !valid_package_name(name) {
            return Err(io::Error::new(io::ErrorKind::InvalidInput, "invalid package name").into());
        }
        args.extend(["--uri".into(), format!("apt://{name}")]);
    }
    let value = claw_os_sdk::cos_call_json("desktop", "launch", args)?;
    if value["launched"] != true || value["app_id"] != "com.clawos.Store"
        || value["launcher"] != "/usr/bin/cosmic-store"
    {
        return Err(cos_runtime::BridgeError::Decode {
            app: "desktop".into(), verb: "launch".into(),
            message: "provider did not confirm native Store launch".into(),
        });
    }
    Ok(())
}

pub fn valid_package_name(name: &str) -> bool {
    name.len() <= 255 && regex::Regex::new(r"^[a-z0-9][a-z0-9+.-]*(?::[a-z0-9][a-z0-9-]*)?$")
        .expect("static package pattern").is_match(name)
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/product.rs"));
}
