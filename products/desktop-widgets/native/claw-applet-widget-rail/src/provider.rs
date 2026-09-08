// SPDX-License-Identifier: GPL-3.0-only

use std::{future::Future, pin::Pin, sync::Arc};

pub type DataFuture<T> = Pin<Box<dyn Future<Output = Result<T, String>> + Send>>;

/// Read-only, independently authorized OS data sources. No provider invokes an App.
#[derive(Clone)]
pub struct Providers {
    pub calendar: Arc<dyn Fn() -> DataFuture<Vec<CalendarEvent>> + Send + Sync>,
    pub tasks: Arc<dyn Fn() -> DataFuture<Vec<Task>> + Send + Sync>,
    pub system: Arc<dyn Fn() -> DataFuture<SystemSummary> + Send + Sync>,
}

impl Providers {
    pub fn new(
        calendar: impl Fn() -> DataFuture<Vec<CalendarEvent>> + Send + Sync + 'static,
        tasks: impl Fn() -> DataFuture<Vec<Task>> + Send + Sync + 'static,
        system: impl Fn() -> DataFuture<SystemSummary> + Send + Sync + 'static,
    ) -> Self {
        Self {
            calendar: Arc::new(calendar),
            tasks: Arc::new(tasks),
            system: Arc::new(system),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CalendarEvent {
    pub id: String,
    pub title: String,
    pub start: String,
    pub end: Option<String>,
    pub location: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Task {
    pub id: String,
    pub purpose: String,
    pub status: String,
    pub created_at: String,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct SystemSummary {
    pub cpu_percent: Option<f32>,
    pub memory: Option<Usage>,
    pub storage: Option<Usage>,
    pub network_down_bps: Option<u64>,
    pub network_up_bps: Option<u64>,
    pub fallback: bool,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Usage {
    pub used_mb: u64,
    pub total_mb: u64,
}

impl Usage {
    pub fn percent(self) -> u64 {
        if self.total_mb == 0 {
            0
        } else {
            self.used_mb.saturating_mul(100) / self.total_mb
        }
    }
}
