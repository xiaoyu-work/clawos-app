// Copyright 2023 System76 <info@system76.com>
// SPDX-License-Identifier: MPL-2.0

use num_derive::{FromPrimitive, ToPrimitive};
use tokio::sync::mpsc;

#[derive(Debug, Clone)]
pub enum AccessibilityEvent {
    Bound(u32),
    Magnifier(bool),
    ScreenFilter { inverted: bool, filter: Option<ColorFilter> },
    Error(String),
    Closed,
}

#[derive(Debug, Default, Clone, Copy, PartialEq, Eq, FromPrimitive, ToPrimitive)]
pub enum ColorFilter {
    Greyscale,
    Deuteranopia,
    Protanopia,
    Tritanopia,
    #[default]
    Unknown,
}

#[derive(Debug, Clone, Copy)]
pub enum AccessibilityRequest {
    Magnifier(bool),
    ScreenFilter { inverted: bool, filter: Option<ColorFilter> },
}

pub type Sender = mpsc::UnboundedSender<AccessibilityRequest>;

pub fn spawn_wayland_connection(
    _minimum: u32,
) -> Result<(Sender, mpsc::Receiver<AccessibilityEvent>), String> {
    let handle = tokio::runtime::Handle::try_current().map_err(|error| error.to_string())?;
    let (events, receiver) = mpsc::channel(8);
    let (sender, mut requests) = mpsc::unbounded_channel();
    handle.spawn(async move {
        loop {
            match cosmic_settings_provider_client::call_async("accessibility", "status", vec![]).await {
                Ok(value) => {
                    let state = &value["cosmic_wayland"];
                    let version = state["protocol_version"].as_u64().and_then(|value| u32::try_from(value).ok());
                    if let (Some(version), Some(magnifier)) = (version, state["magnifier"].as_bool()) {
                        if events.send(AccessibilityEvent::Bound(version)).await.is_err()
                            || events.send(AccessibilityEvent::Magnifier(magnifier)).await.is_err() { return; }
                        if version >= 2 {
                            let filter = if state["filter_active"].as_bool() == Some(false) { None }
                                else { match state["filter"].as_str() {
                                    Some("greyscale") => Some(ColorFilter::Greyscale),
                                    Some("deuteranopia") => Some(ColorFilter::Deuteranopia),
                                    Some("protanopia") => Some(ColorFilter::Protanopia),
                                    Some("tritanopia") => Some(ColorFilter::Tritanopia),
                                    Some(_) => Some(ColorFilter::Unknown),
                                    None => None,
                                }};
                            if events.send(AccessibilityEvent::ScreenFilter {
                                inverted: state["inverted"].as_bool().unwrap_or(false), filter,
                            }).await.is_err() { return; }
                        }
                    } else if events.send(AccessibilityEvent::Closed).await.is_err() { return; }
                }
                Err(error) => {
                    if events.send(AccessibilityEvent::Error(error)).await.is_err()
                        || events.send(AccessibilityEvent::Closed).await.is_err() { return; }
                }
            }
            let request = tokio::select! {
                request = requests.recv() => match request { Some(request) => Some(request), None => return },
                _ = tokio::time::sleep(std::time::Duration::from_secs(2)) => None,
            };
            if let Some(request) = request {
                let changes = match request {
                    AccessibilityRequest::Magnifier(enabled) =>
                        vec![("magnifier", if enabled { "on" } else { "off" })],
                    AccessibilityRequest::ScreenFilter { inverted, filter } => vec![
                        ("invert", if inverted { "on" } else { "off" }),
                        ("filter", match filter {
                            Some(ColorFilter::Greyscale) => "greyscale",
                            Some(ColorFilter::Deuteranopia) => "deuteranopia",
                            Some(ColorFilter::Protanopia) => "protanopia",
                            Some(ColorFilter::Tritanopia) => "tritanopia",
                            Some(ColorFilter::Unknown) | None => "off",
                        }),
                    ],
                };
                for (action, value) in changes {
                    if let Err(error) = cosmic_settings_provider_client::call_async(
                        "accessibility", action, vec!["--value".into(), value.into()],
                    ).await {
                        if events.send(AccessibilityEvent::Error(error)).await.is_err() { return; }
                        break;
                    }
                }
            }
        }
    });
    Ok((sender, receiver))
}
