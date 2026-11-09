// SPDX-License-Identifier: GPL-3.0-only

mod app;
mod provider;
pub use provider::{CalendarEvent, DataFuture, Providers, SystemSummary, Task, Usage};
mod localize;
mod mcp;
mod service;

use localize::localize;

pub fn run_installed() -> cosmic::iced::Result {
    run(service::providers())
}

pub fn run_mcp() -> Result<(), Box<dyn std::error::Error>> {
    mcp::run()
}

pub fn run(providers: Providers) -> cosmic::iced::Result {
    localize();
    cosmic::applet::run::<app::WidgetRail>(providers)
}
