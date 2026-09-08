// SPDX-License-Identifier: GPL-3.0-only

mod app;
mod provider;
pub use provider::{CalendarEvent, DataFuture, Providers, SystemSummary, Task, Usage};
mod localize;

use localize::localize;

pub fn run(providers: Providers) -> cosmic::iced::Result {
    localize();
    cosmic::applet::run::<app::WidgetRail>(providers)
}
