// Copyright 2024 System76 <info@system76.com>
// SPDX-License-Identifier: MPL-2.0

use crate::{Connection, Event, backend};
use futures::SinkExt;

pub async fn watch(_: Connection, mut sender: futures::channel::mpsc::Sender<Event>) {
    loop {
        match backend::snapshot().await {
            Ok(snapshot) => {
                if sender
                    .send(Event::SetAdapters(snapshot.adapters))
                    .await
                    .is_err()
                    || sender
                        .send(Event::SetDevices(snapshot.devices))
                        .await
                        .is_err()
                {
                    return;
                }
            }
            Err(error) => {
                if sender.send(backend::error(error)).await.is_err() {
                    return;
                }
            }
        }
        tokio::time::sleep(std::time::Duration::from_secs(2)).await;
    }
}
