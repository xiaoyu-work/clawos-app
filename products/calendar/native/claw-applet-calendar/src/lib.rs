// SPDX-License-Identifier: GPL-3.0-only

mod app;
mod localize;
mod service;

use jiff::civil::Date;
use std::{future::Future, pin::Pin};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CalendarEvent {
    pub id: String,
    pub title: String,
    pub start: String,
    pub end: Option<String>,
    pub location: String,
}

pub type AgendaFuture = Pin<Box<dyn Future<Output = Result<Vec<CalendarEvent>, String>> + Send>>;
pub type AgendaProvider = fn(Date) -> AgendaFuture;

pub fn run_installed() -> cosmic::iced::Result {
    run(service::agenda)
}

/// Presentation owns no authority; the standalone entry uses the OS SDK provider.
pub fn run(provider: AgendaProvider) -> cosmic::iced::Result {
    localize::localize();
    cosmic::applet::run::<app::CalendarApplet>(provider)
}
