// SPDX-License-Identifier: GPL-3.0-only

use cosmic::iced::futures::{self, SinkExt, Stream};
use cosmic::iced::{Subscription, stream};
use std::{any::TypeId, future};
use tokio::sync::mpsc;

use crate::mpris_backend;
use crate::{Message, MprisMeta, MprisState};

fn watcher_stream() -> impl Stream<Item = Message> {
    stream::channel(5, move |mut messages: futures::channel::mpsc::Sender<Message>| async move {
        let (events, mut event_rx) = mpsc::unbounded_channel();
        let (commands, mut command_rx) = mpsc::channel(5);
        let meta = MprisMeta::default();
        let state = MprisState::default();
        if messages.send(Message::MprisChannel(meta.clone(), state.clone(), events)).await.is_err() {
            return;
        }
        match mpris_backend::start(commands, meta, state).await {
            Ok(server) => loop {
                tokio::select! {
                    Some(command) = command_rx.recv() => {
                        if messages.send(Message::MprisCommand(command)).await.is_err() { break; }
                    }
                    Some(event) = event_rx.recv() => {
                        if let Err(error) = mpris_backend::publish(&server, event).await {
                            log::warn!("failed to publish playback state: {error}");
                        }
                    }
                    else => break,
                }
            },
            Err(error) => log::warn!("failed to start MPRIS server: {error}"),
        }
        future::pending().await
    })
}

#[cold]
pub fn subscription() -> Subscription<Message> {
    struct MprisSubscription;
    Subscription::run_with(TypeId::of::<MprisSubscription>(), |_| watcher_stream())
}
