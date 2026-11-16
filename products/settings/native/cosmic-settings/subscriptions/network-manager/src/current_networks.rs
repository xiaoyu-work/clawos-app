// Copyright 2024 System76 <info@system76.com>
// SPDX-License-Identifier: MPL-2.0

use cosmic_dbus_networkmanager::interface::enums::ActiveConnectionState;
use std::net::Ipv4Addr;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ActiveConnectionInfo {
    Wired {
        name: String,
        hw_address: String,
        speed: u32,
        ip_addresses: Vec<Ipv4Addr>,
    },
    WiFi {
        name: String,
        ip_addresses: Vec<Ipv4Addr>,
        hw_address: String,
        state: ActiveConnectionState,
        strength: u8,
    },
    Vpn {
        name: String,
        ip_addresses: Vec<Ipv4Addr>,
    },
}
impl ActiveConnectionInfo {
    pub fn name(&self) -> String {
        match self {
            Self::Wired { name, .. } | Self::WiFi { name, .. } | Self::Vpn { name, .. } => {
                name.clone()
            }
        }
    }
}
