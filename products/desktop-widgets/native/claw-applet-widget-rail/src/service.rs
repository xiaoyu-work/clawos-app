// SPDX-License-Identifier: GPL-3.0-only

use std::{path::PathBuf, time::Duration};

use claw_os_sdk::applet;
use jiff::civil::Date;
use serde_json::Value;

use crate::{CalendarEvent, Providers, SystemSummary, Task, Usage};

pub fn providers() -> Providers {
    let calendar = Client::installed();
    let tasks = Client::installed();
    let system = Client::installed();
    Providers::new(
        move || {
            let client = calendar.clone();
            Box::pin(async move {
                client
                    .calendar_today()
                    .await
                    .map(|events| events.into_iter().map(calendar_event).collect())
                    .map_err(|error| error.to_string())
            })
        },
        move || {
            let client = tasks.clone();
            Box::pin(async move {
                client
                    .tasks()
                    .await
                    .map(|tasks| tasks.into_iter().map(task).collect())
                    .map_err(|error| error.to_string())
            })
        },
        move || {
            let client = system.clone();
            Box::pin(async move {
                client
                    .system()
                    .await
                    .map(system_summary)
                    .map_err(|error| error.to_string())
            })
        },
    )
}

#[derive(Clone)]
pub(crate) struct Client {
    binary: PathBuf,
}

impl Client {
    pub(crate) fn installed() -> Self {
        Self { binary: "/usr/local/bin/cos".into() }
    }

    #[cfg(test)]
    pub(crate) fn with_binary(binary: PathBuf) -> Self {
        assert!(binary.is_absolute());
        Self { binary }
    }

    async fn call(&self, family: &str, verb: &str, args: Vec<String>) -> Result<Value, String> {
        tokio::time::timeout(Duration::from_secs(12),
            claw_os_sdk::cos_call_json_async_with_binary(&self.binary, family, verb, args),
        ).await.map_err(|_| format!("The OS {family} service timed out."))?
            .map_err(|error| error.to_string())
    }

    pub(crate) async fn calendar_today(&self) -> Result<Vec<applet::CalendarEvent>, String> {
        let day = jiff::Zoned::now().date();
        self.calendar_day(day).await
    }

    async fn calendar_day(&self, day: Date) -> Result<Vec<applet::CalendarEvent>, String> {
        let value = self.call("calendar", "day", vec!["__calendar".into(), "day".into(),
            day.year().to_string(), day.month().to_string(), day.day().to_string()]).await?;
        serde_json::from_value(value.get("events").cloned()
            .ok_or("The OS Calendar service returned no events field.")?)
            .map_err(|error| format!("The OS Calendar service returned invalid events: {error}"))
    }

    pub(crate) async fn tasks(&self) -> Result<Vec<applet::Task>, String> {
        let value = self.call("observe", "tasks", vec!["__observe".into(), "tasks".into()]).await?;
        serde_json::from_value(value.get("tasks").cloned()
            .ok_or("The OS task observer returned no task list.")?)
            .map_err(|error| format!("The OS task observer returned invalid tasks: {error}"))
    }

    pub(crate) async fn system(&self) -> Result<applet::SystemSummary, String> {
        let value = self.call("observe", "resources", vec!["__observe".into(), "resources".into()]).await?;
        serde_json::from_value(value.get("summary").cloned()
            .ok_or("The OS resource observer returned no summary field.")?)
            .map_err(|error| format!("The OS resource observer returned invalid telemetry: {error}"))
    }
}

fn calendar_event(event: applet::CalendarEvent) -> CalendarEvent {
    CalendarEvent {
        id: event.id,
        title: event.title,
        start: event.start,
        end: event.end,
        location: event.location,
    }
}

fn task(task: applet::Task) -> Task {
    Task {
        id: task.id,
        purpose: task.purpose,
        status: task.status,
        created_at: task.created_at,
    }
}

fn system_summary(summary: applet::SystemSummary) -> SystemSummary {
    let usage = |value: applet::Usage| Usage {
        used_mb: value.used_mb,
        total_mb: value.total_mb,
    };
    SystemSummary {
        cpu_percent: summary.cpu_percent,
        memory: summary.memory.map(usage),
        storage: summary.storage.map(usage),
        network_down_bps: summary.network_down_bps,
        network_up_bps: summary.network_up_bps,
        fallback: summary.fallback,
    }
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/service.rs"));
}
