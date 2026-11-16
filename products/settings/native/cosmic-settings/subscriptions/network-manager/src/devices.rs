// Copyright 2024 System76 <info@system76.com>
// SPDX-License-Identifier: MPL-2.0

pub use cosmic_dbus_networkmanager::interface::enums::{
    ActiveConnectionState, DeviceState, DeviceType,
};
use std::sync::Arc;
use zbus::zvariant::ObjectPath;

#[derive(Debug, Clone, Eq, PartialEq)]
pub struct DeviceInfo {
    pub path: ObjectPath<'static>,
    pub device_type: DeviceType,
    pub interface: String,
    pub state: DeviceState,
    pub active_connection: Option<(DeviceConnection, ActiveConnectionState)>,
    pub available_connections: Vec<DeviceConnection>,
    pub known_connections: Vec<KnownDeviceConnection>,
}
#[derive(Debug, Clone, Eq, PartialEq)]
pub struct DeviceConnection {
    pub path: ObjectPath<'static>,
    pub id: String,
    pub uuid: Arc<str>,
}
#[derive(Debug, Clone, Eq, PartialEq)]
pub struct KnownDeviceConnection {
    pub id: String,
    pub uuid: Arc<str>,
}

pub async fn list(
    _: &super::Connection,
    filter: fn(DeviceType) -> bool,
) -> Result<Vec<DeviceInfo>, super::Error> {
    super::provider::snapshot()
        .await
        .and_then(|value| super::provider::devices(&value))
        .map(|devices| {
            devices
                .into_iter()
                .filter(|device| filter(device.device_type))
                .collect()
        })
        .map_err(super::Error::Provider)
}
