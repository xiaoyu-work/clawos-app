// Copyright 2024 System76 <info@system76.com>
// SPDX-License-Identifier: MPL-2.0

use crate::{Connection, Event, backend};
use futures::{SinkExt, channel::oneshot};
use serde_json::Value;
use std::sync::{Arc, Mutex, OnceLock};
use zbus::zvariant::OwnedObjectPath;

#[derive(Clone)]
struct Pair {
    id: String,
    path: OwnedObjectPath,
}
static PAIRS: OnceLock<Mutex<Vec<Pair>>> = OnceLock::new();

pub(crate) fn retain(path: OwnedObjectPath, value: &Value) -> Result<(), String> {
    let id = value["pairing_id"]
        .as_str()
        .filter(|id| id.len() == 32 && id.bytes().all(|byte| byte.is_ascii_hexdigit()))
        .ok_or("OS pairing correlation is unconfirmed")?;
    let mut pairs = PAIRS.get_or_init(|| Mutex::new(Vec::new())).lock().unwrap();
    if pairs.len() >= 8 {
        return Err("OS pairing capacity reached; cancel before retrying".into());
    }
    if !pairs.iter().any(|pair| pair.id == id) {
        pairs.push(Pair {
            id: id.into(),
            path,
        });
    }
    Ok(())
}

fn remove(id: &str) {
    PAIRS
        .get_or_init(|| Mutex::new(Vec::new()))
        .lock()
        .unwrap()
        .retain(|pair| pair.id != id);
}

async fn cancel(id: &str) -> Result<(), String> {
    let value = cosmic_settings_provider_client::call_async(
        "bluetooth",
        "pair-cancel",
        vec!["--pairing-id".into(), id.into()],
    )
    .await?;
    if value["pairing_id"].as_str() != Some(id) || value["status"].as_str() != Some("canceled") {
        return Err("OS pairing cancellation is unconfirmed".into());
    }
    remove(id);
    Ok(())
}

async fn respond(id: &str, yes: bool) -> Result<(), String> {
    cosmic_settings_provider_client::call_stdin_async(
        "bluetooth",
        "pair-respond",
        vec!["--pairing-id".into(), id.into(), "--response-stdin".into()],
        if yes { b"yes\n" } else { b"no\n" },
    )
    .await?;
    Ok(())
}

pub async fn unregister(_: Connection) -> zbus::Result<()> {
    let pairs = PAIRS
        .get_or_init(|| Mutex::new(Vec::new()))
        .lock()
        .unwrap()
        .clone();
    for pair in pairs {
        cancel(&pair.id).await.map_err(|error| {
            zbus::Error::Failure(cosmic_settings_provider_client::refused(error))
        })?;
    }
    Ok(())
}

pub async fn watch(_: Connection, mut sender: futures::channel::mpsc::Sender<Event>) {
    loop {
        let pairs = PAIRS
            .get_or_init(|| Mutex::new(Vec::new()))
            .lock()
            .unwrap()
            .clone();
        for pair in pairs {
            if let Err(error) = poll(&pair, &mut sender).await {
                if sender.send(backend::error(error)).await.is_err() {
                    return;
                }
                if let Err(error) = cancel(&pair.id).await {
                    if sender.send(backend::error(error)).await.is_err() {
                        return;
                    }
                }
            }
        }
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
        if sender.flush().await.is_err() {
            return;
        }
    }
}

async fn poll(
    pair: &Pair,
    sender: &mut futures::channel::mpsc::Sender<Event>,
) -> Result<(), String> {
    let value = cosmic_settings_provider_client::call_async(
        "bluetooth",
        "pair-status",
        vec!["--pairing-id".into(), pair.id.clone()],
    )
    .await?;
    let device = backend::known_device(&pair.path)?;
    if value["pairing_id"].as_str() != Some(&pair.id)
        || value["device"].as_str() != Some(&device.address)
        || value["adapter"].as_str() != Some(&backend::adapter(&device.adapter)?)
    {
        return Err("OS pairing returned a different device or correlation".into());
    }
    match value["status"].as_str() {
        Some("paired") => {
            remove(&pair.id);
            backend::device_action("connect", &pair.path).await?;
        }
        Some("failed" | "canceled") => {
            remove(&pair.id);
            sender
                .send(Event::DeviceFailed(pair.path.clone()))
                .await
                .map_err(|_| "pairing UI closed")?;
        }
        Some("pending") if value["needs_response"].as_bool() == Some(true) => {
            match value["prompt"]["kind"].as_str() {
                Some("authorization") => respond(&pair.id, true).await?,
                Some("confirmation") => {
                    let passkey = value["prompt"]["message"]
                        .as_str()
                        .and_then(|message| {
                            message
                                .split(|ch: char| !ch.is_ascii_digit())
                                .find(|token| token.len() == 6)
                        })
                        .and_then(|value| value.parse::<u32>().ok())
                        .ok_or("OS pairing passkey is unconfirmed")?;
                    let (response, receive) = oneshot::channel();
                    sender
                        .send(Event::Agent(Arc::new(
                            bluez_zbus::agent1::Message::RequestConfirmation {
                                device: pair.path.clone(),
                                passkey,
                                response,
                            },
                        )))
                        .await
                        .map_err(|_| "pairing UI closed")?;
                    match receive.await {
                        Ok(yes) => respond(&pair.id, yes).await?,
                        Err(_) => cancel(&pair.id).await?,
                    }
                }
                Some("pin-code" | "passkey") => {
                    cancel(&pair.id).await?;
                    return Err("This retained confirmation UI cannot enter a device PIN/passkey; the OS pairing was canceled.".into());
                }
                _ => return Err("OS pairing prompt is unavailable".into()),
            }
        }
        Some("pending") => {}
        _ => return Err("OS pairing outcome is unconfirmed".into()),
    }
    Ok(())
}
