// Copyright 2024 System76 <info@system76.com>
// SPDX-License-Identifier: MPL-2.0

pub mod available_wifi;
pub mod current_networks;
pub mod devices;
pub mod hw_address;
mod provider;
pub use cosmic_dbus_networkmanager as dbus;
pub use provider::{
    Connection, connect, import_profile, operation, profile, profiles, save_profile, vpn_connect,
};

use available_wifi::{AccessPoint, NetworkType};
use current_networks::ActiveConnectionInfo;
use dbus::interface::enums::NmConnectivityState;
use futures::{
    SinkExt, StreamExt,
    channel::mpsc::{UnboundedSender, unbounded},
};
use secure_string::SecureString;
use std::{sync::Arc, time::Duration};
use zbus::zvariant::ObjectPath;

pub type SSID = Arc<str>;
pub type UUID = Arc<str>;

#[derive(thiserror::Error, Debug)]
pub enum Error {
    #[error("{0}")]
    Provider(String),
}

#[derive(Debug, Clone)]
pub enum Request {
    Activate(ObjectPath<'static>, ObjectPath<'static>),
    Deactivate(UUID),
    Disconnect(SSID),
    Forget(SSID),
    Authenticate {
        ssid: String,
        identity: Option<String>,
        password: SecureString,
        interface: Option<String>,
    },
    GetWiFiCredentials(SSID, UUID, NetworkType),
    Reload,
    Remove(UUID),
    SelectAccessPoint(SSID, NetworkType, Option<String>),
    SetAirplaneMode(bool),
    SetWiFi(bool),
}

#[derive(Debug, Clone)]
pub enum Event {
    RequestResponse {
        req: Request,
        state: NetworkManagerState,
        success: bool,
    },
    Init {
        conn: Connection,
        sender: UnboundedSender<Request>,
        state: NetworkManagerState,
    },
    Error(String),
    WiFiCredentials {
        ssid: SSID,
        password: Option<SecureString>,
        security_type: NetworkType,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NetworkManagerState {
    pub wireless_access_points: Vec<AccessPoint>,
    pub active_conns: Vec<ActiveConnectionInfo>,
    pub known_access_points: Vec<AccessPoint>,
    pub wifi_enabled: bool,
    pub airplane_mode: bool,
    pub connectivity: NmConnectivityState,
}
impl NetworkManagerState {
    pub async fn new(_: &Connection) -> Result<Self, Error> {
        provider::snapshot()
            .await
            .and_then(|value| provider::state(&value))
            .map_err(Error::Provider)
    }
}

pub async fn watch(conn: Connection, mut output: futures::channel::mpsc::Sender<Event>) {
    let mut previous = match NetworkManagerState::new(&conn).await {
        Ok(state) => state,
        Err(error) => {
            let _ = output
                .send(Event::Error(cosmic_settings_provider_client::refused(
                    error,
                )))
                .await;
            return;
        }
    };
    let (sender, mut receiver) = unbounded();
    if output
        .send(Event::Init {
            conn,
            sender,
            state: previous.clone(),
        })
        .await
        .is_err()
    {
        return;
    }
    loop {
        let request = tokio::select! {
            request=receiver.next()=>match request {Some(request)=>request,None=>return},
            _=tokio::time::sleep(Duration::from_secs(5))=>Request::Reload,
        };
        let mut success = match provider::execute(&request, &mut output).await {
            Ok(()) => true,
            Err(error) => {
                if output
                    .send(Event::Error(cosmic_settings_provider_client::refused(
                        error,
                    )))
                    .await
                    .is_err()
                {
                    return;
                }
                false
            }
        };
        match provider::snapshot()
            .await
            .and_then(|value| provider::state(&value))
        {
            Ok(state) => previous = state,
            Err(error) => {
                success = false;
                if output
                    .send(Event::Error(cosmic_settings_provider_client::refused(
                        error,
                    )))
                    .await
                    .is_err()
                {
                    return;
                }
            }
        }
        if output
            .send(Event::RequestResponse {
                req: request,
                state: previous.clone(),
                success,
            })
            .await
            .is_err()
        {
            return;
        }
    }
}
