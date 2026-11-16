use crate::{Active, Adapter, Device, Event};
use serde_json::Value;
use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};
use zbus::zvariant::OwnedObjectPath;

pub type Connection = ();
static CACHE: OnceLock<Mutex<Option<Snapshot>>> = OnceLock::new();

#[derive(Clone, Default)]
pub(crate) struct Snapshot {
    pub adapters: HashMap<OwnedObjectPath, Adapter>,
    pub devices: HashMap<OwnedObjectPath, Device>,
}

pub async fn connect() -> zbus::Result<Connection> {
    snapshot().await.map(|_| ()).map_err(zbus::Error::Failure)
}

pub(crate) fn error(error: impl std::fmt::Display) -> Event {
    Event::DBusError(zbus::Error::Failure(
        cosmic_settings_provider_client::refused(error),
    ))
}

pub(crate) fn event(result: Result<(), String>) -> Event {
    match result {
        Ok(()) => Event::Ok,
        Err(message) => error(message),
    }
}

pub(crate) fn adapter(path: &OwnedObjectPath) -> Result<String, String> {
    CACHE
        .get_or_init(|| Mutex::new(None))
        .lock()
        .unwrap()
        .as_ref()
        .and_then(|snapshot| snapshot.adapters.get(path))
        .map(|adapter| adapter.address.clone())
        .ok_or_else(|| "Bluetooth adapter changed; refresh before retrying".into())
}

pub(crate) fn known_device(path: &OwnedObjectPath) -> Result<Device, String> {
    CACHE
        .get_or_init(|| Mutex::new(None))
        .lock()
        .unwrap()
        .as_ref()
        .and_then(|snapshot| snapshot.devices.get(path))
        .cloned()
        .ok_or_else(|| "Bluetooth device changed; refresh before retrying".into())
}

pub(crate) async fn device_action(action: &str, path: &OwnedObjectPath) -> Result<Value, String> {
    let device = known_device(path)?;
    cosmic_settings_provider_client::call_async(
        "bluetooth",
        action,
        vec![
            "--adapter".into(),
            adapter(&device.adapter)?,
            "--device".into(),
            device.address,
        ],
    )
    .await
}

pub(crate) async fn snapshot() -> Result<Snapshot, String> {
    let value = cosmic_settings_provider_client::call_async("bluetooth", "status", vec![]).await?;
    let snapshot = parse(value).map_err(cosmic_settings_provider_client::refused)?;
    *CACHE.get_or_init(|| Mutex::new(None)).lock().unwrap() = Some(snapshot.clone());
    Ok(snapshot)
}

fn text(value: &Value) -> Result<String, String> {
    value
        .as_str()
        .filter(|value| value.len() <= 1024)
        .map(str::to_owned)
        .ok_or_else(|| "OS Bluetooth metadata is missing or oversized".into())
}

fn address(value: &Value) -> Result<String, String> {
    let value = text(value)?;
    if value.len() != 17
        || value.split(':').count() != 6
        || !value
            .split(':')
            .all(|part| part.len() == 2 && part.bytes().all(|byte| byte.is_ascii_hexdigit()))
    {
        return Err("OS Bluetooth address is invalid".into());
    }
    Ok(value)
}

fn active(value: &Value) -> Result<Active, String> {
    value
        .as_bool()
        .map(|value| {
            if value {
                Active::Enabled
            } else {
                Active::Disabled
            }
        })
        .ok_or_else(|| "OS Bluetooth state is unconfirmed".into())
}

fn parse(value: Value) -> Result<Snapshot, String> {
    if value["provider"].as_str() != Some("bluez") || value["available"].as_bool() != Some(true) {
        return Err("OS Bluetooth backend is unavailable".into());
    }
    if value["errors"]
        .as_array()
        .is_some_and(|errors| !errors.is_empty())
    {
        return Err(
            "OS Bluetooth inventory is incomplete; refresh before changing a device".into(),
        );
    }
    let adapters = value["adapters"]
        .as_array()
        .filter(|values| values.len() <= 32)
        .ok_or("invalid OS Bluetooth adapter collection")?;
    let mut snapshot = Snapshot::default();
    for data in adapters {
        let path: OwnedObjectPath = text(&data["object_path"])?
            .try_into()
            .map_err(|_| "invalid OS Bluetooth path")?;
        let properties = &data["properties"];
        snapshot.adapters.insert(
            path.clone(),
            Adapter {
                alias: text(
                    properties
                        .get("alias")
                        .or_else(|| properties.get("name"))
                        .unwrap_or(&data["name"]),
                )?,
                address: address(&data["address"])?,
                scanning: active(&properties["discovering"])?,
                enabled: active(&properties["powered"])?,
            },
        );
        for data in data["devices"]
            .as_array()
            .filter(|values| values.len() <= 100)
            .ok_or("invalid OS Bluetooth device collection")?
        {
            let address = address(&data["address"])?;
            let object_path: OwnedObjectPath =
                format!("{}/dev_{}", path, address.replace(':', "_"))
                    .try_into()
                    .map_err(|_| "invalid OS Bluetooth device path")?;
            let battery = data["battery_percentage"].as_str().and_then(|value| {
                value
                    .split_once('(')
                    .map(|(_, rest)| rest.trim_end_matches(')'))
                    .unwrap_or(value)
                    .parse::<u8>()
                    .ok()
                    .filter(|value| *value <= 100)
                    .map(|value| value.to_string())
            });
            snapshot.devices.insert(
                object_path,
                Device {
                    alias: data["alias"]
                        .as_str()
                        .or_else(|| data["name"].as_str())
                        .map(str::to_owned),
                    address,
                    adapter: path.clone(),
                    enabled: active(&data["connected"])?,
                    paired: data["paired"]
                        .as_bool()
                        .ok_or("OS Bluetooth pairing state is unconfirmed")?,
                    icon: crate::device::icon(data["icon"].as_str().unwrap_or_default()),
                    battery,
                },
            );
        }
    }
    Ok(snapshot)
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/backend.rs"));
}
