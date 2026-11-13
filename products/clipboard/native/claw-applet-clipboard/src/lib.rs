// SPDX-License-Identifier: GPL-3.0-only

mod app;
mod copyq;
mod localize;
mod mcp;
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
    run_with_policy(None)
}

pub fn run_mcp() -> Result<(), Box<dyn std::error::Error>> {
    mcp::run()
}

/// Preserve the linked shell's optional policy seam; Root still authorizes every operation.
pub fn run(policy: HistoryPolicy) -> cosmic::iced::Result {
    run_with_policy(Some(policy))
}

fn run_with_policy(policy: Option<HistoryPolicy>) -> cosmic::iced::Result {
    localize::localize();
    let settings = cosmic::applet::Context::default()
        .window_settings()
        .no_main_window(true);
    cosmic::app::run::<app::ClipboardApplet>(settings, policy)
}
