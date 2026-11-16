// Copyright 2023 System76 <info@system76.com>
// SPDX-License-Identifier: GPL-3.0-only

use futures::SinkExt;
use iced_futures::{Subscription, stream};
use tokio::sync::mpsc::UnboundedSender;

#[derive(Debug, Clone)]
pub enum Response {
    Error(String),
    IsEnabled(bool),
    ScreenReader(bool),
    Init(bool, UnboundedSender<Request>),
}

pub enum Request {
    Enable(bool),
    ScreenReader(bool),
}

pub fn subscription() -> Subscription<Response> {
    Subscription::run_with(std::any::TypeId::of::<Response>(), |_| {
        stream::channel(4, |mut output: futures::channel::mpsc::Sender<Response>| async move {
            let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel();
            let mut first = true;
            loop {
                match cosmic_settings_provider_client::call_async("accessibility", "status", vec![]).await {
                    Ok(value) => {
                        let atspi = &value["atspi"];
                        if let (Some(enabled), Some(reader)) = (
                            atspi["is_enabled"].as_bool(), atspi["screen_reader_enabled"].as_bool(),
                        ) {
                            if first {
                                first = false;
                                if output.send(Response::Init(reader, tx.clone())).await.is_err() { return; }
                            }
                            if output.send(Response::IsEnabled(enabled)).await.is_err()
                                || output.send(Response::ScreenReader(reader)).await.is_err() { return; }
                        } else if output.send(Response::Error(
                            cosmic_settings_provider_client::refused("The OS accessibility backend is unavailable."),
                        )).await.is_err() { return; }
                    }
                    Err(error) => {
                        if output.send(Response::Error(error)).await.is_err() { return; }
                    }
                }
                let request = tokio::select! {
                    request = rx.recv() => match request { Some(request) => Some(request), None => return },
                    _ = tokio::time::sleep(std::time::Duration::from_secs(2)) => None,
                };
                if let Some(request) = request {
                    let enabled = match request {
                        Request::ScreenReader(enabled) => enabled,
                        Request::Enable(_) => {
                            if output.send(Response::Error(cosmic_settings_provider_client::refused(
                                "The OS exposes the complete screen-reader switch, not an independent raw accessibility bus switch.",
                            ))).await.is_err() { return; }
                            continue;
                        }
                    };
                    if let Err(error) = cosmic_settings_provider_client::call_async(
                        "accessibility", "screen-reader",
                        vec!["--value".into(), if enabled { "on" } else { "off" }.into()],
                    ).await
                        && output.send(Response::Error(error)).await.is_err() { return; }
                }
            }
        })
    })
}
