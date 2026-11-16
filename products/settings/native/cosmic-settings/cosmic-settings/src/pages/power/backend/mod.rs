// Copyright 2023 System76 <info@system76.com>
// SPDX-License-Identifier: GPL-3.0-only

use jiff::{Span, SpanRelativeTo, SpanRound, ToSpan, Unit};
use serde_json::Value;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PowerProfile {
    Battery,
    Balanced,
    Performance,
}

impl PowerProfile {
    fn parse(value: &Value) -> Result<Self, String> {
        match value.as_str() {
            Some("battery") => Ok(Self::Battery),
            Some("balanced") => Ok(Self::Balanced),
            Some("performance") => Ok(Self::Performance),
            _ => Err(cosmic_settings_provider_client::refused(
                "OS power profile is unconfirmed",
            )),
        }
    }

    fn name(self) -> &'static str {
        match self {
            Self::Battery => "battery",
            Self::Balanced => "balanced",
            Self::Performance => "performance",
        }
    }

    pub fn title(&self) -> String {
        match self {
            Self::Battery => fl!("power-mode", "battery"),
            Self::Balanced => fl!("power-mode", "balanced"),
            Self::Performance => fl!("power-mode", "performance"),
        }
    }

    pub fn description(&self) -> String {
        match self {
            Self::Battery => fl!("power-mode", "battery-desc"),
            Self::Balanced => fl!("power-mode", "balanced-desc"),
            Self::Performance => fl!("power-mode", "performance-desc"),
        }
    }
}

pub fn get_power_profiles() -> Vec<PowerProfile> {
    vec![
        PowerProfile::Battery,
        PowerProfile::Balanced,
        PowerProfile::Performance,
    ]
}

#[derive(Debug, Clone)]
pub struct PowerBackendEnum {
    pub current: PowerProfile,
}

pub async fn get_backend() -> Option<PowerBackendEnum> {
    match cosmic_settings_provider_client::call_async("power", "profile-status", vec![]).await {
        Ok(value) if value["action"].as_str() == Some("profile-status") => {
            PowerProfile::parse(&value["profile"])
                .ok()
                .map(|current| PowerBackendEnum { current })
        }
        Ok(_) => {
            cosmic_settings_provider_client::refused("OS power profile observation is unconfirmed");
            None
        }
        Err(_) => None,
    }
}

impl PowerBackendEnum {
    pub async fn set_power_profile(&self, requested: PowerProfile) -> Result<PowerProfile, String> {
        let action = format!("profile-{}", requested.name());
        let value = cosmic_settings_provider_client::call_async("power", &action, vec![]).await?;
        if value["action"].as_str() != Some(&action)
            || value["status"].as_str() != Some("applied")
            || PowerProfile::parse(&value["profile"])? != requested
        {
            return Err(cosmic_settings_provider_client::refused(
                "OS did not confirm the requested power profile",
            ));
        }
        Ok(requested)
    }
}

#[derive(Default, Debug, Clone)]
pub struct Battery {
    pub icon_name: String,
    pub is_present: bool,
    pub percent: f64,
    pub is_charging: bool,
    pub remaining_duration: Span,
}

#[derive(Default, Debug, Clone)]
pub struct ConnectedDevice {
    pub model: String,
    pub device_icon: &'static str,
    pub battery: Battery,
    pub device_path: String,
}

#[derive(Debug, Clone)]
pub struct Snapshot {
    pub battery: Battery,
    pub devices: Vec<ConnectedDevice>,
}

pub async fn snapshot() -> Result<Snapshot, String> {
    parse_snapshot(cosmic_settings_provider_client::call_async("power", "status", vec![]).await?)
        .map_err(cosmic_settings_provider_client::refused)
}

fn field<'a>(properties: &'a Value, name: &str) -> Option<&'a Value> {
    properties.get(name).or_else(|| {
        properties
            .as_object()?
            .iter()
            .find(|(key, _)| {
                key.rsplit_once('.')
                    .is_some_and(|(_, suffix)| suffix == name)
            })
            .map(|(_, value)| value)
    })
}

fn battery(properties: &Value, system: bool) -> Result<Battery, String> {
    let present = field(properties, "present")
        .and_then(Value::as_bool)
        .or_else(|| (!system).then_some(true))
        .ok_or("OS battery presence is unavailable")?;
    if !present {
        return Ok(Battery::default());
    }
    let percent = field(properties, "percentage")
        .and_then(Value::as_f64)
        .filter(|value| value.is_finite() && (0.0..=100.0).contains(value))
        .ok_or("OS battery percentage is unavailable")?;
    let state = field(properties, "state")
        .and_then(Value::as_str)
        .ok_or("OS battery state is unavailable")?;
    let is_charging = state == "charging";
    let remaining_duration = field(
        properties,
        if is_charging {
            "time_to_full"
        } else {
            "time_to_empty"
        },
    )
    .and_then(Value::as_str)
    .and_then(|value| {
        let mut fields = value.split_whitespace();
        let number = fields.next()?.parse::<f64>().ok()?;
        let scale = match fields.next()? {
            "second" | "seconds" => 1.0,
            "minute" | "minutes" => 60.0,
            "hour" | "hours" => 3600.0,
            "day" | "days" => 86400.0,
            _ => return None,
        };
        let seconds = number * scale;
        (seconds.is_finite() && (0.0..=31_536_000.0).contains(&seconds))
            .then(|| (seconds.round() as i64).seconds())
    })
    .unwrap_or_default();
    let level = [
        (95.0, 100),
        (80.0, 90),
        (65.0, 80),
        (35.0, 50),
        (20.0, 35),
        (14.0, 20),
        (9.0, 10),
        (5.0, 5),
    ]
    .into_iter()
    .find(|(minimum, _)| percent > *minimum)
    .map_or(0, |(_, level)| level);
    let suffix = if is_charging || state == "fully-charged" {
        "charging-"
    } else {
        ""
    };
    Ok(Battery {
        icon_name: format!("cosmic-applet-battery-level-{level}-{suffix}symbolic"),
        is_present: present,
        percent,
        is_charging,
        remaining_duration,
    })
}

fn parse_snapshot(value: Value) -> Result<Snapshot, String> {
    let system = &value["display_device"];
    if system.get("error").is_some() {
        return Err("OS system battery observation is unavailable".into());
    }
    let battery = battery(&system["properties"], true)?;
    let entries = value["devices"]
        .as_array()
        .filter(|entries| entries.len() <= 32)
        .ok_or("invalid OS power device collection")?;
    let mut devices = Vec::new();
    for entry in entries {
        let path = entry["object_path"]
            .as_str()
            .filter(|path| path.starts_with("/org/freedesktop/UPower/devices/"))
            .ok_or("OS power device identity is unavailable")?;
        let properties = &entry["properties"];
        let kind = properties.as_object().and_then(|properties| {
            properties
                .keys()
                .filter_map(|key| key.split_once('.').map(|(prefix, _)| prefix))
                .find(|prefix| !matches!(*prefix, "line_power" | "battery"))
        });
        let Some(kind) = kind else {
            continue;
        };
        let icon = match kind {
            "mouse" => "input-mouse-symbolic",
            "keyboard" => "input-keyboard-symbolic",
            "phone" | "pda" => "smartphone-symbolic",
            "tablet" => "tablet-symbolic",
            "computer" => "laptop-symbolic",
            "headset" => "audio-headset-symbolic",
            "headphones" => "audio-headphones-symbolic",
            "speakers" => "speaker-symbolic",
            "gaming_input" => "input-gaming-symbolic",
            "touchpad" => "input-touchpad-symbolic",
            "monitor" => "display-symbolic",
            "ups" => "uninterruptible-power-supply-symbolic",
            _ => "bluetooth-symbolic",
        };
        devices.push(ConnectedDevice {
            model: field(properties, "model")
                .and_then(Value::as_str)
                .map(str::to_owned)
                .unwrap_or_else(|| fl!("connected-devices", "unknown")),
            device_icon: icon,
            battery: battery_from_entry(properties)?,
            device_path: path.into(),
        });
    }
    Ok(Snapshot { battery, devices })
}

fn battery_from_entry(properties: &Value) -> Result<Battery, String> {
    battery(properties, false)
}

impl Battery {
    pub fn remaining_time(&self) -> String {
        if !self.remaining_duration.is_positive() {
            return String::new();
        }
        let balanced = self
            .remaining_duration
            .round(
                SpanRound::new()
                    .largest(Unit::Day)
                    .relative(SpanRelativeTo::days_are_24_hours()),
            )
            .unwrap();
        let mut time = Vec::new();
        if balanced.get_days() > 0 {
            time.push(fl!("battery", "day", value = balanced.get_days()));
        }
        if balanced.get_hours() > 0 {
            time.push(fl!("battery", "hour", value = balanced.get_hours()));
        }
        if balanced.get_minutes() > 0 {
            time.push(fl!("battery", "minute", value = balanced.get_minutes()));
        }
        if time.len() == 3 {
            let last = time.pop().unwrap();
            time = vec![time.join(", "), last];
        }
        let time = if time.is_empty() {
            fl!("battery", "less-than-minute")
        } else {
            time.join(&format!(" {} ", fl!("battery", "and")))
        };
        fl!(
            "battery",
            "remaining-time",
            time = time,
            action = if self.is_charging { "full" } else { "empty" }
        )
    }
}

#[cfg(test)]
mod tests {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/unit/pages/power/backend.rs"
    ));
}
