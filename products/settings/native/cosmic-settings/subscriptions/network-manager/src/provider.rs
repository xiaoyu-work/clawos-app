use crate::available_wifi::{AccessPoint, NetworkType};
use crate::current_networks::ActiveConnectionInfo;
use crate::dbus::interface::enums::NmConnectivityState;
use crate::devices::{
    ActiveConnectionState, DeviceConnection, DeviceInfo, DeviceState, DeviceType,
    KnownDeviceConnection,
};
use crate::hw_address::HwAddress;
use crate::{Error, Event, NetworkManagerState, Request};
use futures::SinkExt;
use serde_json::{Value, json};
use std::{collections::BTreeMap, sync::Arc};
use zbus::zvariant::ObjectPath;

#[derive(Debug, Clone)]
pub struct Connection;

pub async fn connect() -> Result<Connection, Error> {
    snapshot()
        .await
        .and_then(|value| state(&value))
        .map(|_| Connection)
        .map_err(Error::Provider)
}
pub(crate) async fn snapshot() -> Result<Value, String> {
    let value =
        cosmic_settings_provider_client::call_async("network", "native-status", vec![]).await?;
    validate(&value)?;
    Ok(value)
}
fn validate(value: &Value) -> Result<(), String> {
    if value["version"] != 1 || value["provider"] != "networkmanager" {
        return Err("OS network snapshot version/provider is unconfirmed".into());
    }
    array(value, "profiles", 256)?;
    array(value, "devices", 32)?;
    array(value, "access_points", 512)?;
    array(value, "active", 128)?;
    Ok(())
}
fn array<'a>(value: &'a Value, key: &str, max: usize) -> Result<&'a Vec<Value>, String> {
    value[key]
        .as_array()
        .filter(|values| values.len() <= max)
        .ok_or_else(|| format!("OS network {key} inventory is unavailable or unbounded"))
}
fn string<'a>(value: &'a Value, key: &str) -> Result<&'a str, String> {
    value[key]
        .as_str()
        .filter(|text| text.len() <= 1024 && !text.contains('\0'))
        .ok_or_else(|| format!("OS network {key} metadata is unavailable"))
}
fn path(value: &Value, key: &str) -> Result<ObjectPath<'static>, String> {
    ObjectPath::try_from(string(value, key)?.to_string())
        .map_err(|_| "OS network metadata path is invalid".into())
}
fn number(value: &Value, key: &str, max: u64) -> Result<u32, String> {
    value[key]
        .as_u64()
        .filter(|value| *value <= max)
        .map(|value| value as u32)
        .ok_or_else(|| format!("OS network {key} number is unavailable"))
}
fn profile_by_uuid<'a>(value: &'a Value, id: &str) -> Result<&'a Value, String> {
    array(value, "profiles", 256)?
        .iter()
        .find(|value| value["uuid"].as_str() == Some(id))
        .ok_or_else(|| "OS network profile is no longer available".into())
}
pub async fn profiles() -> Result<Vec<Value>, String> {
    Ok(array(&snapshot().await?, "profiles", 256)?.clone())
}
pub async fn profile(uuid: &str) -> Result<Value, String> {
    let value = post("profile-read", json!({"target":uuid})).await?;
    value
        .get("profile")
        .cloned()
        .filter(Value::is_object)
        .ok_or_else(|| "OS network profile is unavailable".into())
}
async fn post(action: &str, value: Value) -> Result<Value, String> {
    let bytes = serde_json::to_vec(&value).map_err(|_| "encode network request")?;
    cosmic_settings_provider_client::call_stdin_async(
        "network",
        action,
        vec!["--request-stdin".into()],
        &bytes,
    )
    .await
}
pub async fn save_profile(value: Value) -> Result<Value, String> {
    let result = post("profile-save", json!({"profile":value})).await?;
    if result["action"] != "profile-save" || result["status"] != "applied" {
        return Err("OS network profile save is unconfirmed".into());
    }
    result
        .get("profile")
        .cloned()
        .ok_or_else(|| "OS saved profile metadata unavailable".into())
}
pub async fn import_profile(kind: &str, name: &str, content: String) -> Result<(), String> {
    let result = post(
        "profile-import",
        json!({"config":{"kind":kind,"name":name,"content":content}}),
    )
    .await?;
    if result["action"] != "profile-import" || result["status"] != "applied" {
        return Err("OS VPN profile import is unconfirmed".into());
    }
    Ok(())
}
pub async fn operation(action: &str, uuid: &str, credential: Option<&str>) -> Result<(), String> {
    operation_at(action, uuid, credential, None).await
}
async fn operation_at(
    action: &str,
    uuid: &str,
    credential: Option<&str>,
    interface: Option<&str>,
) -> Result<(), String> {
    if let Some(reference) = credential {
        validate_reference(reference)?;
    }
    let result = post(
        action,
        json!({"target":uuid,"credential":credential,"interface":interface}),
    )
    .await?;
    if result["action"] != action || result["status"] != "applied" || result["target"] != uuid {
        return Err("OS network operation is unconfirmed".into());
    }
    Ok(())
}
pub async fn vpn_connect(
    uuid: &str,
    username: Option<String>,
    credential: Option<&str>,
) -> Result<(), String> {
    if let Some(reference) = credential {
        validate_reference(reference)?;
    }
    let mut profile_change = None;
    if let Some(username) = username {
        let mut current = profile(uuid).await?;
        if current["username"].as_str() != Some(username.as_str()) {
            current["username"] = json!(username);
            profile_change = Some(current);
        }
    }
    let result = post(
        "vpn-connect",
        json!({"target":uuid,"credential":credential,"profile":profile_change}),
    )
    .await?;
    if result["action"] != "vpn-connect"
        || result["status"] != "applied"
        || result["target"] != uuid
    {
        return Err("OS VPN connection is unconfirmed".into());
    }
    Ok(())
}
fn validate_reference(value: &str) -> Result<(), String> {
    let Some((namespace, name)) = value.split_once('/') else {
        return Err(
            "Enter an OS credential reference (namespace/name), never a plaintext password.".into(),
        );
    };
    let valid = |value: &str| {
        !value.is_empty()
            && value.len() <= 255
            && !value.starts_with('-')
            && value.bytes().all(|byte| {
                byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.' | b':')
            })
    };
    if !valid(namespace) || !valid(name) {
        return Err(
            "Enter an OS credential reference (namespace/name), never a plaintext password.".into(),
        );
    }
    Ok(())
}
pub(crate) fn devices(value: &Value) -> Result<Vec<DeviceInfo>, String> {
    validate(value)?;
    let mut result = Vec::new();
    for data in array(value, "devices", 32)? {
        let kind = match number(data, "kind", u32::MAX as u64)? {
            1 => DeviceType::Ethernet,
            2 => DeviceType::Wifi,
            29 => DeviceType::WireGuard,
            _ => return Err("OS network device type is unsupported".into()),
        };
        let mut available = Vec::new();
        for path in array(data, "available", 256)? {
            let path = path
                .as_str()
                .ok_or("OS available profile path is unavailable")?;
            if let Some(profile) = array(value, "profiles", 256)?
                .iter()
                .find(|profile| profile["path"].as_str() == Some(path))
            {
                available.push(connection(profile)?);
            }
        }
        let active = array(value, "active", 128)?
            .iter()
            .find(|active| active["path"] == data["active"]);
        let active_connection = match active {
            Some(active) => Some((
                connection(profile_by_uuid(value, string(active, "uuid")?)?)?,
                ActiveConnectionState::from(number(active, "state", 4)?),
            )),
            None => None,
        };
        let known = available
            .iter()
            .map(|connection| KnownDeviceConnection {
                id: connection.id.clone(),
                uuid: connection.uuid.clone(),
            })
            .collect();
        result.push(DeviceInfo {
            path: path(data, "path")?,
            device_type: kind,
            interface: string(data, "interface")?.into(),
            state: DeviceState::from(number(data, "state", 120)?),
            active_connection,
            available_connections: available,
            known_connections: known,
        });
    }
    Ok(result)
}
fn connection(data: &Value) -> Result<DeviceConnection, String> {
    Ok(DeviceConnection {
        path: path(data, "path")?,
        id: string(data, "name")?.into(),
        uuid: Arc::from(string(data, "uuid")?),
    })
}
fn network_type(value: &str) -> Result<NetworkType, String> {
    match value {
        "open" => Ok(NetworkType::Open),
        "psk" => Ok(NetworkType::PskOrSae),
        "eap" => Ok(NetworkType::EAP),
        _ => Err("OS Wi-Fi security is not supported by this UI".into()),
    }
}
pub(crate) fn state(value: &Value) -> Result<NetworkManagerState, String> {
    validate(value)?;
    let mut aps = BTreeMap::<String, AccessPoint>::new();
    for data in array(value, "access_points", 512)? {
        let security = string(data, "security")?;
        if security == "unsupported" {
            continue;
        }
        let ssid = string(data, "ssid")?;
        if ssid.is_empty() {
            continue;
        }
        let strength = number(data, "strength", 100)? as u8;
        if aps.get(ssid).is_some_and(|ap| ap.strength >= strength) {
            continue;
        }
        aps.insert(
            ssid.into(),
            AccessPoint {
                ssid: Arc::from(ssid),
                strength,
                state: DeviceState::from(number(data, "state", 120)?),
                working: false,
                path: path(data, "path")?,
                hw_address: HwAddress::from_str(string(data, "hw_address")?)
                    .ok_or("OS Wi-Fi hardware address unavailable")?,
                secured: data["secured"]
                    .as_bool()
                    .ok_or("OS Wi-Fi security state unavailable")?,
                wps_push: data["wps_push"]
                    .as_bool()
                    .ok_or("OS Wi-Fi WPS state unavailable")?,
                network_type: network_type(security)?,
            },
        );
    }
    let mut known = Vec::new();
    for profile in array(value, "profiles", 256)?
        .iter()
        .filter(|profile| profile["kind"] == "wifi")
    {
        let ssid = string(profile, "ssid")?;
        if let Some(ap) = aps.get(ssid) {
            known.push(ap.clone());
        }
    }
    let mut wireless = aps.into_values().collect::<Vec<_>>();
    wireless.sort_by(|left, right| right.strength.cmp(&left.strength));
    let mut active = Vec::new();
    for data in array(value, "active", 128)? {
        let profile = profile_by_uuid(value, string(data, "uuid")?)?;
        let ip_addresses = array(data, "ip_addresses", 32)?
            .iter()
            .map(|address| {
                address
                    .as_str()
                    .ok_or("OS network address unavailable")
                    .and_then(|value| value.parse().map_err(|_| "OS IPv4 address invalid"))
            })
            .collect::<Result<Vec<_>, _>>()?;
        let device = array(value, "devices", 32)?
            .iter()
            .find(|device| device["active"] == data["path"]);
        match string(data, "kind")? {
            "vpn" | "wireguard" => active.push(ActiveConnectionInfo::Vpn {
                name: string(data, "name")?.into(),
                ip_addresses,
            }),
            "ethernet" => {
                let device = device.ok_or("OS active Ethernet device unavailable")?;
                active.push(ActiveConnectionInfo::Wired {
                    name: string(data, "name")?.into(),
                    hw_address: string(device, "hw_address")?.into(),
                    speed: number(device, "speed", u32::MAX as u64)?,
                    ip_addresses,
                });
            }
            "wifi" => {
                let device = device.ok_or("OS active Wi-Fi device unavailable")?;
                let ssid = string(profile, "ssid")?;
                let strength = wireless
                    .iter()
                    .find(|ap| ap.ssid.as_ref() == ssid)
                    .map(|ap| ap.strength)
                    .unwrap_or(0);
                active.push(ActiveConnectionInfo::WiFi {
                    name: ssid.into(),
                    ip_addresses,
                    hw_address: string(device, "hw_address")?.into(),
                    state: ActiveConnectionState::from(number(data, "state", 4)?),
                    strength,
                });
            }
            _ => return Err("OS active network type is unsupported".into()),
        }
    }
    Ok(NetworkManagerState {
        wireless_access_points: wireless,
        known_access_points: known,
        active_conns: active,
        wifi_enabled: value["wifi_enabled"]
            .as_bool()
            .ok_or("OS Wi-Fi enabled state unavailable")?,
        airplane_mode: value["airplane_mode"]
            .as_bool()
            .ok_or("OS airplane state unavailable")?,
        connectivity: NmConnectivityState::from(number(value, "connectivity", 4)?),
    })
}
pub(crate) async fn execute(
    request: &Request,
    output: &mut futures::channel::mpsc::Sender<Event>,
) -> Result<(), String> {
    match request {
        Request::Reload => return Ok(()),
        Request::SetAirplaneMode(state) | Request::SetWiFi(state) => {
            let action = if matches!(request, Request::SetWiFi(_)) {
                "wifi-toggle"
            } else {
                "airplane"
            };
            cosmic_settings_provider_client::call_async(
                "network",
                action,
                vec!["--state".into(), if *state { "on" } else { "off" }.into()],
            )
            .await?;
            return Ok(());
        }
        Request::Authenticate { password, .. } => validate_reference(password.unsecure())?,
        _ => {}
    }
    let snapshot = snapshot().await?;
    match request {
        Request::Activate(device, path) => {
            let device = array(&snapshot, "devices", 32)?
                .iter()
                .find(|data| data["path"].as_str() == Some(device.as_str()))
                .ok_or("selected device is no longer available")?;
            if device["kind"] != 1 {
                return Err("Ethernet activation requires an Ethernet device".into());
            }
            let profile = array(&snapshot, "profiles", 256)?
                .iter()
                .find(|data| data["path"].as_str() == Some(path.as_str()))
                .ok_or("selected profile is no longer available")?;
            operation_at(
                "ethernet-up",
                string(profile, "uuid")?,
                None,
                Some(string(device, "interface")?),
            )
            .await
        }
        Request::Deactivate(uuid) | Request::Remove(uuid) => {
            let profile = profile_by_uuid(&snapshot, uuid)?;
            let action = match (
                string(profile, "kind")?,
                matches!(request, Request::Remove(_)),
            ) {
                ("ethernet", true) => "ethernet-remove",
                ("ethernet", false) => "ethernet-down",
                ("wifi", true) => "wifi-remove",
                ("wifi", false) => "wifi-down",
                ("vpn" | "wireguard", true) => "vpn-remove",
                ("vpn" | "wireguard", false) => "vpn-deactivate",
                _ => return Err("network profile category is unsupported".into()),
            };
            operation(action, uuid, None).await
        }
        Request::Forget(ssid)
        | Request::Disconnect(ssid)
        | Request::SelectAccessPoint(ssid, _, _) => {
            let matches = array(&snapshot, "profiles", 256)?
                .iter()
                .filter(|profile| {
                    profile["kind"] == "wifi" && profile["ssid"].as_str() == Some(ssid.as_ref())
                })
                .collect::<Vec<_>>();
            if matches.len() > 1 {
                return Err(
                    "multiple saved profiles have this SSID; select an exact profile".into(),
                );
            }
            let profile = matches.first().copied();
            if let Request::SelectAccessPoint(_, security, interface) = request {
                if let Some(profile) = profile {
                    return operation_at(
                        "wifi-up",
                        string(profile, "uuid")?,
                        None,
                        interface.as_deref(),
                    )
                    .await;
                }
                if *security != NetworkType::Open {
                    return Err(
                        "An OS credential reference is required for this protected network.".into(),
                    );
                }
                let result=post("wifi-join",json!({"profile":{"kind":"wifi","name":ssid.as_ref(),"ssid":ssid.as_ref(),"security":"open","interface":interface,"autoconnect":true,"ipv4_method":"auto"},"interface":interface})).await?;
                if result["action"] != "wifi-join" || result["status"] != "applied" {
                    return Err("OS Wi-Fi connection is unconfirmed".into());
                }
                return Ok(());
            }
            let profile = profile.ok_or("saved Wi-Fi profile is no longer available")?;
            operation(
                if matches!(request, Request::Forget(_)) {
                    "wifi-remove"
                } else {
                    "wifi-down"
                },
                string(profile, "uuid")?,
                None,
            )
            .await
        }
        Request::Authenticate {
            ssid,
            identity,
            password,
            interface,
        } => {
            let mut profiles = array(&snapshot, "profiles", 256)?.iter().filter(|profile| {
                profile["kind"] == "wifi" && profile["ssid"].as_str() == Some(ssid)
            });
            let existing = profiles.next();
            if profiles.next().is_some() {
                return Err(
                    "multiple saved profiles have this SSID; select an exact profile".into(),
                );
            }
            let mut profile = if let Some(existing) = existing {
                profile(string(existing, "uuid")?).await?
            } else {
                json!({"kind":"wifi","name":ssid,"ssid":ssid,"security":if identity.is_some(){"eap"}else{"psk"},"identity":identity,"interface":interface,"autoconnect":true,"ipv4_method":"auto"})
            };
            if identity.is_some() {
                profile["identity"] = json!(identity);
            }
            let result = post(
                "wifi-join",
                json!({"profile":profile,"credential":password.unsecure(),"interface":interface}),
            )
            .await?;
            if result["action"] != "wifi-join" || result["status"] != "applied" {
                return Err("OS Wi-Fi connection is unconfirmed".into());
            }
            Ok(())
        }
        Request::GetWiFiCredentials(ssid, uuid, security) => {
            if *security == NetworkType::Open {
                let current = state(&snapshot)?;
                if !current
                    .wireless_access_points
                    .iter()
                    .any(|point| point.ssid == *ssid && point.network_type == NetworkType::Open)
                {
                    return Err("open Wi-Fi metadata changed; refresh before sharing".into());
                }
                return output
                    .send(Event::WiFiCredentials {
                        ssid: ssid.clone(),
                        password: None,
                        security_type: *security,
                    })
                    .await
                    .map_err(|_| "Wi-Fi sharing UI closed".into());
            }
            let value = post("wifi-share", json!({"target":uuid.as_ref()})).await?;
            if value["uuid"].as_str() != Some(uuid.as_ref())
                || value["ssid"].as_str() != Some(ssid.as_ref())
                || network_type(string(&value, "security")?)? != *security
            {
                return Err("OS Wi-Fi sharing returned a different profile".into());
            }
            let password = value["password"]
                .as_str()
                .map(secure_string::SecureString::from);
            if *security != NetworkType::Open && password.is_none() {
                return Err("OS Wi-Fi sharing did not return credentials".into());
            }
            output
                .send(Event::WiFiCredentials {
                    ssid: ssid.clone(),
                    password,
                    security_type: *security,
                })
                .await
                .map_err(|_| "Wi-Fi sharing UI closed".into())
        }
        _ => Ok(()),
    }
}

#[cfg(test)]
mod tests {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/unit/provider.rs"
    ));
}
