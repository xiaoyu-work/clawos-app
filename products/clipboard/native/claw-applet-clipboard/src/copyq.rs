// SPDX-License-Identifier: GPL-3.0-only

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::service::{self, HistoryAction};

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ClipboardEntry {
    pub identity: String,
    pub preview: String,
    pub copied_at: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Snapshot {
    entries: Vec<ClipboardEntry>,
}

pub async fn load_history() -> Result<Vec<ClipboardEntry>, String> {
    snapshot(service::history(HistoryAction::List, None, false, None).await?)
}

pub async fn restore(identity: String) -> Result<(), String> {
    outcome(
        service::history(HistoryAction::Restore, Some(&identity), false, None).await?,
        "restored",
    )
}

pub async fn remove(identity: String) -> Result<(), String> {
    outcome(
        service::history(HistoryAction::Remove, Some(&identity), false, None).await?,
        "removed",
    )
}

pub async fn clear() -> Result<(), String> {
    outcome(
        service::history(HistoryAction::Clear, None, true, None).await?,
        "cleared",
    )
}

fn snapshot(value: Value) -> Result<Vec<ClipboardEntry>, String> {
    let value: Snapshot = serde_json::from_value(value)
        .map_err(|_| "OS clipboard history returned an invalid snapshot")?;
    if value.entries.len() > 20
        || value.entries.iter().any(|entry| {
            !service::valid_identity(&entry.identity)
                || entry.preview.contains('\0')
                || entry.preview.chars().count() > 181
                || entry
                    .copied_at
                    .as_ref()
                    .is_some_and(|time| time.chars().count() > 256)
        })
    {
        return Err("OS clipboard history exceeded its record limits".into());
    }
    Ok(value.entries)
}

fn outcome(value: Value, field: &str) -> Result<(), String> {
    if value
        .as_object()
        .is_some_and(|object| object.len() == 1 && object.get(field) == Some(&Value::Bool(true)))
    {
        Ok(())
    } else {
        Err(
            "OS clipboard history did not confirm the action; inspect history before retrying"
                .into(),
        )
    }
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/copyq.rs"));
}
