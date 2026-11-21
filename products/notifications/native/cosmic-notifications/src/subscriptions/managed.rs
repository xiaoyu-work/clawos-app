// SPDX-License-Identifier: GPL-3.0-only

// Private Host presentation resource; neither an owner bus nor an inbox client.

use std::collections::HashMap;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use claw_notification_presentation::{Card, Icon, Preferences};
use cosmic::iced::{
    Subscription,
    futures::{self, SinkExt},
    stream,
};
use cosmic_notifications_util::{CloseReason, Notification};
use serde::Deserialize;
use serde_json::{Value, json};
use tokio::sync::mpsc;

use super::notifications::{Event, Input};

pub fn enabled() -> bool {
    std::env::var("COS_APP_GUI").as_deref() == Ok("1")
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Reply {
    version: u32,
    command: Option<Command>,
}

#[derive(Debug, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
enum Command {
    Present {
        handle: u32,
        token: String,
        app_name: String,
        icon: String,
        summary: String,
        body: String,
        urgency: u8,
        expire_ms: i32,
        transient: bool,
        replaces: Option<u32>,
    },
    Close {
        handle: u32,
        token: String,
    },
    Dismiss {
        handle: u32,
        token: String,
    },
    Activate {
        handle: u32,
        token: String,
        action: String,
    },
    Preferences {
        request_id: String,
        muted: bool,
    },
}

struct Entry {
    token: String,
    notification: Notification,
    accepted: bool,
    activated: bool,
}

async fn exchange(event: Option<Value>) -> Result<Reply> {
    let payload = json!({"event":event}).to_string();
    let value = claw_os_sdk::cos_call_json_async_with_stdin_binary(
        "/usr/local/bin/yu",
        "notification",
        "presentation",
        ["__gui_notifications", "--request-stdin"],
        payload.as_bytes(),
    )
    .await?;
    let reply: Reply = serde_json::from_value(value)?;
    anyhow::ensure!(
        reply.version == 1,
        "unsupported native notification presentation version"
    );
    Ok(reply)
}

pub fn subscription() -> Subscription<Event> {
    struct ManagedNotifications;
    Subscription::run_with(std::any::TypeId::of::<ManagedNotifications>(), |_| {
        stream::channel(
            100,
            |mut output: futures::channel::mpsc::Sender<Event>| async move {
                if let Err(error) = run(&mut output).await {
                    let _ = output.send(Event::Unavailable(error.to_string())).await;
                }
                futures::future::pending::<()>().await;
            },
        )
    })
}

async fn run(output: &mut futures::channel::mpsc::Sender<Event>) -> Result<()> {
    let config = crate::presentation::config()?;
    let preferences = crate::presentation::preferences(&config)?;
    let (sender, mut input) = mpsc::channel(100);
    output.send(Event::Ready(sender)).await?;
    let mut event = Some(json!({"kind":"preferences","preferences":preferences,"request_id":null}));
    let mut entries: HashMap<u32, Entry> = HashMap::new();
    loop {
        let reply = exchange(event.take()).await?;
        if let Some(command) = reply.command {
            match command {
                Command::Present {
                    handle,
                    token,
                    app_name,
                    icon,
                    summary,
                    body,
                    urgency,
                    expire_ms,
                    transient,
                    replaces,
                } => {
                    validate_ticket(handle, &token)?;
                    if !entries
                        .get(&handle)
                        .is_some_and(|entry| entry.token == token)
                    {
                        let hints = HashMap::from([
                            ("urgency", zbus::zvariant::Value::U8(urgency)),
                            ("transient", zbus::zvariant::Value::Bool(transient)),
                        ]);
                        let notification = Notification::new(
                            &app_name,
                            handle,
                            &icon,
                            &summary,
                            &body,
                            vec!["default", "Acknowledge"],
                            hints,
                            expire_ms,
                        );
                        let replacing = entries.contains_key(&handle);
                        entries.insert(
                            handle,
                            Entry {
                                token,
                                notification: notification.clone(),
                                accepted: false,
                                activated: false,
                            },
                        );
                        output
                            .send(if let Some(previous) = replaces {
                                anyhow::ensure!(
                                    previous != handle && entries.contains_key(&previous),
                                    "invalid native replacement handle"
                                );
                                Event::ReplaceHandle {
                                    previous,
                                    notification,
                                }
                            } else if replacing {
                                Event::Replace(notification)
                            } else {
                                Event::Notification(notification)
                            })
                            .await?;
                    }
                }
                Command::Close { handle, token } => {
                    matched(&entries, handle, &token)?;
                    output.send(Event::CloseNotification(handle)).await?;
                }
                Command::Dismiss { handle, token } => {
                    matched(&entries, handle, &token)?;
                    output.send(Event::DismissNotification(handle)).await?;
                }
                Command::Activate {
                    handle,
                    token,
                    action,
                } => {
                    matched(&entries, handle, &token)?;
                    anyhow::ensure!(action == "default", "notification action is not declared");
                    output
                        .send(Event::AppletActivated {
                            id: handle,
                            action: action.parse().unwrap(),
                        })
                        .await?;
                }
                Command::Preferences { request_id, muted } => {
                    validate_ticket(1, &request_id)?;
                    let preferences = crate::presentation::set_preferences(
                        &config,
                        &Preferences::new(muted).to_json()?,
                    )?;
                    output.send(Event::Preferences(preferences.clone())).await?;
                    event = Some(
                        json!({"kind":"preferences","preferences":preferences,"request_id":request_id}),
                    );
                    continue;
                }
            }
        }
        let next = tokio::select! {
            next = input.recv() => Some(next.context("native notification controls closed")?),
            _ = tokio::time::sleep(Duration::from_millis(250)) => None,
        };
        let Some(next) = next else { continue };
        event = feedback(next, &mut entries)?;
    }
}

fn validate_ticket(handle: u32, token: &str) -> Result<()> {
    claw_notification_presentation::validate_handle(handle)?;
    anyhow::ensure!(
        token.len() == 32
            && token
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "invalid native notification correlation"
    );
    Ok(())
}

fn matched<'a>(entries: &'a HashMap<u32, Entry>, handle: u32, token: &str) -> Result<&'a Entry> {
    validate_ticket(handle, token)?;
    entries
        .get(&handle)
        .filter(|entry| entry.token == token)
        .context("native notification handle is stale")
}

fn feedback(input: Input, entries: &mut HashMap<u32, Entry>) -> Result<Option<Value>> {
    let value = match input {
        Input::Presented(handle) => {
            let Some(entry) = entries.get_mut(&handle).filter(|entry| !entry.accepted) else {
                return Ok(None);
            };
            let card = if entry.notification.transient() {
                None
            } else {
                match managed_card(&entry.notification) {
                    Ok(card) => Some(card.to_json()?),
                    Err(error) => {
                        tracing::error!(%error, "native notification card projection failed");
                        return Ok(Some(
                            json!({"kind":"failed","handle":handle,"token":entry.token}),
                        ));
                    }
                }
            };
            entry.accepted = true;
            json!({"kind":"presented","handle":handle,"token":entry.token,"card":card})
        }
        Input::Activated { id, action, .. } => {
            let Some(entry) = entries.get_mut(&id) else {
                return Ok(None);
            };
            anyhow::ensure!(
                action == "default",
                "native notification action is not declared"
            );
            entry.activated = true;
            json!({"kind":"activated","handle":id,"token":entry.token,"action":action})
        }
        Input::Closed(id, reason) => {
            let Some(entry) = entries.remove(&id) else {
                return Ok(None);
            };
            let reason = match reason {
                CloseReason::Dismissed if !entry.activated => "dismissed",
                CloseReason::Expired => "expired",
                _ => "closed",
            };
            json!({"kind":"closed","handle":id,"token":entry.token,"reason":reason})
        }
        Input::PresentationPreferencesChanged(preferences) => {
            json!({"kind":"preferences","preferences":preferences,"request_id":null})
        }
        _ => bail!("a raw-bus notification event reached the private Host subscription"),
    };
    Ok(Some(value))
}

pub fn body_spans(notification: &Notification) -> Vec<cosmic::iced::core::text::Span<'static>> {
    vec![cosmic::iced::core::text::Span::new(
        notification.body.clone(),
    )]
}

fn managed_card(notification: &Notification) -> Result<Card> {
    let mut display = notification.clone();
    display.body.clear();
    let mut card = crate::presentation::card(&display)?;
    card.body = body_spans(notification)
        .into_iter()
        .map(|span| claw_notification_presentation::TextRun {
            text: span.text.into_owned(),
            ..Default::default()
        })
        .collect();
    for icon in [&mut card.icon, &mut card.group_icon].into_iter().flatten() {
        match icon {
            Icon::Rgba {
                width,
                height,
                pixels,
            } if *width > 64 || *height > 64 => {
                let image = image::RgbaImage::from_raw(*width, *height, std::mem::take(pixels))
                    .context("invalid presentation image")?;
                let resized = image::DynamicImage::ImageRgba8(image)
                    .thumbnail(64, 64)
                    .into_rgba8();
                (*width, *height) = resized.dimensions();
                *pixels = resized.into_raw();
            }
            Icon::Mask {
                width,
                height,
                alpha,
            } if *width > 64 || *height > 64 => {
                let image = image::GrayImage::from_raw(*width, *height, std::mem::take(alpha))
                    .context("invalid presentation mask")?;
                let resized = image::DynamicImage::ImageLuma8(image)
                    .thumbnail(64, 64)
                    .into_luma8();
                (*width, *height) = resized.dimensions();
                *alpha = resized.into_raw();
            }
            _ => {}
        }
    }
    card.validate()?;
    anyhow::ensure!(
        card.to_json()?.len() <= 512 * 1024,
        "notification presentation exceeds the Host transport bound"
    );
    Ok(card)
}

#[cfg(test)]
mod tests {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/unit/subscriptions/managed.rs"
    ));
}
