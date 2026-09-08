// SPDX-License-Identifier: GPL-3.0-only

mod app;
mod copyq;
mod localize;

use std::{future::Future, pin::Pin};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HistoryPermission {
    Read,
    Write,
}

pub type PolicyFuture = Pin<Box<dyn Future<Output = Result<(), String>> + Send>>;
pub type HistoryPolicy = fn(HistoryPermission) -> PolicyFuture;

/// The OS host supplies authorization for the named history scope only.
pub fn run(policy: HistoryPolicy) -> cosmic::iced::Result {
    localize::localize();
    cosmic::applet::run::<app::ClipboardApplet>(policy)
}
