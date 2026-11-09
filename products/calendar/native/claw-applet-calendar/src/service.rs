// SPDX-License-Identifier: GPL-3.0-only

use std::{path::PathBuf, time::Duration};

use claw_os_sdk::applet;
use jiff::civil::Date;

use crate::{AgendaFuture, CalendarEvent};

pub fn agenda(day: Date) -> AgendaFuture {
    Box::pin(async move {
        Client::installed()
            .calendar_day(day)
            .await
            .map(|events| events.into_iter().map(calendar_event).collect())
    })
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

    pub(crate) async fn calendar_day(&self, day: Date) -> Result<Vec<applet::CalendarEvent>, String> {
        let args = ["__calendar".into(), "day".into(), day.year().to_string(),
            day.month().to_string(), day.day().to_string()];
        let value = tokio::time::timeout(
            Duration::from_secs(12),
            claw_os_sdk::cos_call_json_async_with_binary(&self.binary, "calendar", "day", args),
        ).await.map_err(|_| "The OS Calendar service timed out.".to_string())?
            .map_err(|error| error.to_string())?;
        let events = value.get("events").cloned()
            .ok_or("The OS Calendar service returned no events field.")?;
        serde_json::from_value(events)
            .map_err(|error| format!("The OS Calendar service returned invalid events: {error}"))
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

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/service.rs"));
}
