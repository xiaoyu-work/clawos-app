// SPDX-License-Identifier: GPL-3.0-only

mod app;
mod copyq;
mod localize;
mod service;

use std::{future::Future, pin::Pin};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HistoryPermission {
    Read,
    Write,
}

pub type PolicyFuture = Pin<Box<dyn Future<Output = Result<(), String>> + Send>>;
pub type HistoryPolicy = fn(HistoryPermission) -> PolicyFuture;

pub fn run_installed() -> cosmic::iced::Result {
    run(service::history_policy)
}

/// The standalone entry obtains only named history authorization from the OS SDK.
pub fn run(policy: HistoryPolicy) -> cosmic::iced::Result {
    localize::localize();
    cosmic::applet::run::<app::ClipboardApplet>(policy)
}
