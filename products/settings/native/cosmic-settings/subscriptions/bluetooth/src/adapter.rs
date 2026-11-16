// Copyright 2024 System76 <info@system76.com>
// SPDX-License-Identifier: MPL-2.0

use crate::{Active, Connection, Event, backend};
use std::hash::{Hash, Hasher};
use zbus::zvariant::OwnedObjectPath;

#[derive(Default, Debug, Clone)]
pub struct Adapter {
    pub alias: String,
    pub address: String,
    pub scanning: Active,
    pub enabled: Active,
}

impl Hash for Adapter {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.address.hash(state);
    }
}
impl PartialEq for Adapter {
    fn eq(&self, other: &Self) -> bool {
        self.address == other.address
    }
}
impl Eq for Adapter {}

impl Adapter {
    pub fn update(&mut self, updates: Vec<AdapterUpdate>) {
        for update in updates {
            match update {
                AdapterUpdate::Alias(value) => self.alias = value,
                AdapterUpdate::Address(value) => self.address = value,
                AdapterUpdate::Enabled(value) => self.enabled = value,
                AdapterUpdate::Scanning(value) => self.scanning = value,
            }
        }
    }
}

#[derive(Debug, Clone)]
pub enum AdapterUpdate {
    Alias(String),
    Address(String),
    Scanning(Active),
    Enabled(Active),
}

static SCAN: tokio::sync::Mutex<Result<(), String>> = tokio::sync::Mutex::const_new(Ok(()));

pub async fn start_discovery(_: Connection, path: OwnedObjectPath) -> Event {
    let mut scan = SCAN.lock().await;
    let result = async {
        let address = backend::adapter(&path)?;
        cosmic_settings_provider_client::call_async(
            "bluetooth",
            "scan",
            vec!["--adapter".into(), address, "--seconds".into(), "5".into()],
        )
        .await?;
        Ok::<(), String>(())
    }
    .await;
    *scan = result.clone();
    backend::event(result)
}

pub async fn stop_discovery(_: Connection, _: OwnedObjectPath) -> Event {
    // The existing Root scan is finite and retires its own BlueZ connection.
    // Waiting for that request is not an unrelated sender's StopDiscovery.
    backend::event(SCAN.lock().await.clone())
}

pub async fn change_adapter_status(_: Connection, path: OwnedObjectPath, active: bool) -> Event {
    backend::event(
        async {
            cosmic_settings_provider_client::call_async(
                "bluetooth",
                "power",
                vec![
                    "--adapter".into(),
                    backend::adapter(&path)?,
                    "--state".into(),
                    if active { "on" } else { "off" }.into(),
                ],
            )
            .await?;
            Ok(())
        }
        .await,
    )
}

pub async fn get_adapters(_: Connection) -> Event {
    match backend::snapshot().await {
        Ok(snapshot) => Event::SetAdapters(snapshot.adapters),
        Err(error) => backend::error(error),
    }
}
