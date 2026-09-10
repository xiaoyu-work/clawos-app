// SPDX-License-Identifier: GPL-3.0-only

use claw_os_sdk::applet::{self, Client};

use crate::{HistoryPermission, PolicyFuture};

pub fn history_policy(permission: HistoryPermission) -> PolicyFuture {
    Box::pin(async move {
        Client::installed()
            .require_history(history_permission(permission))
            .await
            .map_err(|error| error.to_string())
    })
}

fn history_permission(permission: HistoryPermission) -> applet::HistoryPermission {
    match permission {
        HistoryPermission::Read => applet::HistoryPermission::Read,
        HistoryPermission::Write => applet::HistoryPermission::Write,
    }
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/service.rs"));
}
