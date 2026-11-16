// SPDX-License-Identifier: GPL-3.0-only

use std::any::TypeId;
use std::sync::{Arc, Mutex};

use cosmic::iced::futures::{self, SinkExt};
use cosmic::iced::{Subscription, stream};
use serde::Deserialize;
use serde_json::{Value, json};
use tokio::sync::oneshot;

use crate::{Message, PlaybackCommand};

#[derive(Clone, Copy, Debug, Deserialize)]
#[serde(rename_all = "snake_case")]
enum Action {
    Status,
    Play,
    Pause,
    Stop,
    Next,
    Previous,
    Toggle,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Command {
    request_id: String,
    action: Action,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Exchange {
    version: u8,
    command: Option<Command>,
}

#[derive(Clone, Debug)]
pub struct Request {
    action: Action,
    reply: Arc<Mutex<Option<oneshot::Sender<Value>>>>,
}

impl Request {
    pub(crate) fn command(&self) -> Option<PlaybackCommand> {
        Some(match self.action {
            Action::Status => return None,
            Action::Play => PlaybackCommand::Play,
            Action::Pause => PlaybackCommand::Pause,
            Action::Stop => PlaybackCommand::Stop,
            Action::Next => PlaybackCommand::Next,
            Action::Previous => PlaybackCommand::Previous,
            Action::Toggle => PlaybackCommand::Toggle,
        })
    }

    pub(crate) fn take_reply(&self) -> Option<oneshot::Sender<Value>> {
        self.reply
            .lock()
            .expect("native playback reply lock")
            .take()
    }
}

async fn exchange(reply: Option<Value>) -> Result<Option<Command>, String> {
    let value = tokio::task::spawn_blocking(move || {
        claw_os_sdk::cos_call_json_with_stdin(
            "media-player",
            "exchange",
            ["__gui-media", "--request-stdin"],
            json!({"reply":reply}).to_string().as_bytes(),
        )
    })
    .await
    .map_err(|error| error.to_string())?
    .map_err(|error| error.to_string())?;
    let value: Exchange = serde_json::from_value(value)
        .map_err(|_| "OS playback service returned an invalid exchange")?;
    if value.version != 1
        || value.command.as_ref().is_some_and(|command| {
            command.request_id.len() != 32
                || !command
                    .request_id
                    .bytes()
                    .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        })
    {
        return Err("OS playback service returned an invalid correlation".into());
    }
    Ok(value.command)
}

pub(crate) fn subscription() -> Subscription<Message> {
    struct ManagedPlayback;
    Subscription::run_with(TypeId::of::<ManagedPlayback>(), |_| {
        stream::channel(
            5,
            |mut messages: futures::channel::mpsc::Sender<Message>| async move {
                let mut reply = None;
                loop {
                    let command = match exchange(reply.take()).await {
                        Ok(Some(command)) => command,
                        Ok(None) => continue,
                        Err(error) => {
                            log::error!("managed playback service: {error}");
                            break;
                        }
                    };
                    let (sender, receiver) = oneshot::channel();
                    let request = Request {
                        action: command.action,
                        reply: Arc::new(Mutex::new(Some(sender))),
                    };
                    if messages
                        .send(Message::ManagedPlayback(request))
                        .await
                        .is_err()
                    {
                        break;
                    }
                    let result = match receiver.await {
                        Ok(result) => result,
                        Err(_) => {
                            json!({"kind":"failed","error":"native playback UI ended before handling the command"})
                        }
                    };
                    reply = Some(json!({"request_id":command.request_id,"result":result}));
                }
                std::future::pending().await
            },
        )
    })
}
