// Copyright 2024 System76 <info@system76.com>
// SPDX-License-Identifier: MPL-2.0

use super::hw_address::HwAddress;
use cosmic_dbus_networkmanager::interface::enums::DeviceState;
use std::sync::Arc;
use zbus::zvariant::ObjectPath;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AccessPoint {
    pub ssid: Arc<str>,
    pub strength: u8,
    pub state: DeviceState,
    pub working: bool,
    pub path: ObjectPath<'static>,
    pub hw_address: HwAddress,
    pub secured: bool,
    pub wps_push: bool,
    pub network_type: NetworkType,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NetworkType {
    Open,
    PskOrSae,
    EAP,
}
