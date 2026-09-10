// SPDX-License-Identifier: GPL-3.0-only

use claw_os_sdk::applet::{self, Client};
use jiff::civil::Date;

use crate::{AgendaFuture, CalendarEvent};

pub fn agenda(day: Date) -> AgendaFuture {
    Box::pin(async move {
        Client::installed()
            .calendar_day(applet::CalendarDate {
                year: day.year(),
                month: day.month(),
                day: day.day(),
            })
            .await
            .map(|events| events.into_iter().map(calendar_event).collect())
            .map_err(|error| error.to_string())
    })
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
