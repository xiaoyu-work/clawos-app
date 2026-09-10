// SPDX-License-Identifier: GPL-3.0-only

use claw_os_sdk::applet::{self, Client};

use crate::{CalendarEvent, Providers, SystemSummary, Task, Usage};

pub fn providers() -> Providers {
    let calendar = Client::installed();
    let tasks = Client::installed();
    // Independent pipes preserve independent refresh/error states. Only the
    // system client needs to retain its OS process's sampling deltas.
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
