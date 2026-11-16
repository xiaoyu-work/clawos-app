// Copyright 2024 System76 <info@system76.com>
// SPDX-License-Identifier: MPL-2.0

use crate::{Active, Connection, Event, backend};
use std::hash::{Hash, Hasher};
use zbus::zvariant::OwnedObjectPath;

#[derive(Default, Debug, Clone)]
pub struct Device {
    pub(crate) alias: Option<String>,
    pub address: String,
    pub adapter: OwnedObjectPath,
    pub enabled: Active,
    pub paired: bool,
    pub icon: &'static str,
    pub battery: Option<String>,
}

impl Device {
    pub fn is_connected(&self) -> bool {
        self.enabled == Active::Enabled
    }
    pub fn has_alias(&self) -> bool {
        self.alias.is_some()
    }
    pub fn is_known_device_type(&self) -> bool {
        self.icon != "bluetooth-symbolic"
    }
    pub fn alias_or_addr(&self) -> &str {
        self.alias.as_ref().unwrap_or(&self.address)
    }
    pub fn update(&mut self, updates: Vec<DeviceUpdate>) {
        for update in updates {
            match update {
                DeviceUpdate::Alias(value) => self.alias = value,
                DeviceUpdate::Enabled(value) => self.enabled = value,
                DeviceUpdate::Paired(value) => self.paired = value,
                DeviceUpdate::Icon(value) => self.icon = value,
                DeviceUpdate::Battery(value) => self.battery = value,
            }
        }
    }
}

impl Hash for Device {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.address.hash(state);
    }
}
impl PartialEq for Device {
    fn eq(&self, other: &Self) -> bool {
        self.address == other.address
    }
}
impl Eq for Device {}

#[derive(Debug, Clone)]
pub enum DeviceUpdate {
    Alias(Option<String>),
    Enabled(Active),
    Paired(bool),
    Icon(&'static str),
    Battery(Option<String>),
}

pub(crate) fn icon(kind: &str) -> &'static str {
    match kind {
        "computer" => "laptop-symbolic",
        "phone" => "smartphone-symbolic",
        "network-wireless" => "network-wireless-symbolic",
        "audio-headset" => "audio-headset-symbolic",
        "audio-headphones" => "audio-headphones-symbolic",
        "camera-video" => "camera-video-symbolic",
        "audio-card" => "audio-card-symbolic",
        "input-gaming" => "input-gaming-symbolic",
        "input-keyboard" => "input-keyboard-symbolic",
        "input-tablet" => "input-tablet-symbolic",
        "input-mouse" => "input-mouse-symbolic",
        "printer" => "printer-network-symbolic",
        "camera-photo" => "camera-photo-symbolic",
        _ => "bluetooth-symbolic",
    }
}

pub async fn disconnect_device(_: Connection, path: OwnedObjectPath) -> Event {
    backend::event(
        backend::device_action("disconnect", &path)
            .await
            .map(|_| ()),
    )
}

pub async fn connect_device(_: Connection, path: OwnedObjectPath) -> Event {
    backend::event(
        async {
            let device = backend::known_device(&path)?;
            if device.paired {
                backend::device_action("connect", &path).await?;
            } else {
                let value = backend::device_action("pair", &path).await?;
                crate::agent::retain(path, value.get("pairing").unwrap_or(&value))?;
            }
            Ok(())
        }
        .await,
    )
}

pub async fn forget_device(_: Connection, path: OwnedObjectPath) -> Event {
    backend::event(backend::device_action("forget", &path).await.map(|_| ()))
}

pub async fn get_devices(_: Connection, path: OwnedObjectPath) -> Event {
    match backend::snapshot().await {
        Ok(snapshot) => Event::SetDevices(
            snapshot
                .devices
                .into_iter()
                .filter(|(_, device)| device.adapter == path)
                .collect(),
        ),
        Err(error) => backend::error(error),
    }
}
