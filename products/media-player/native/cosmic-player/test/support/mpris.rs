// SPDX-License-Identifier: GPL-3.0-only
//! Headless fixture around the exact native MPRIS backend. No GStreamer,
//! display, user configuration or real media is opened.

#[allow(dead_code)]
#[path = "../../src/config.rs"]
mod config;
#[path = "../../src/playback.rs"]
mod playback;
#[path = "../../src/mpris_backend.rs"]
mod mpris_backend;

use std::io::Write;
use playback::{MprisEvent, MprisMeta, MprisState, PlaybackCommand};
use tokio::io::{AsyncBufReadExt, BufReader};

struct OtherPlayer;

#[zbus::interface(name = "org.mpris.MediaPlayer2.Player")]
impl OtherPlayer {
    fn play(&self) { panic!("another player's Play was selected"); }
    fn pause(&self) { panic!("another player's Pause was selected"); }
    fn stop(&self) { panic!("another player's Stop was selected"); }
    fn next(&self) { panic!("another player's Next was selected"); }
    fn previous(&self) { panic!("another player's Previous was selected"); }
    fn play_pause(&self) { panic!("another player's PlayPause was selected"); }
    #[zbus(property)]
    fn playback_status(&self) -> String { "OtherPlayerMustNeverBeSelected".into() }
}

async fn client(name: &str, action: &str) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    use std::collections::HashMap;
    use zbus::zvariant::OwnedValue;
    let connection = zbus::Connection::session().await?;
    let player = zbus::Proxy::new(&connection, name, "/org/mpris/MediaPlayer2",
        "org.mpris.MediaPlayer2.Player").await?;
    if action == "status" {
        let status: String = player.get_property("PlaybackStatus").await?;
        let mut metadata: HashMap<String, OwnedValue> = player.get_property("Metadata").await?;
        let title = metadata.remove("xesam:title").map(String::try_from).transpose()?;
        let url = metadata.remove("xesam:url").map(String::try_from).transpose()?;
        let album = metadata.remove("xesam:album").map(String::try_from).transpose()?;
        let artist = metadata.remove("xesam:artist").map(Vec::<String>::try_from).transpose()?.unwrap_or_default();
        let length = metadata.remove("mpris:length").map(i64::try_from).transpose()?;
        return Ok(serde_json::json!({"status":status,"title":title,"url":url,
            "album":album,"artist":artist,"length_micros":length}));
    }
    let method = match action {
        "play" => "Play", "pause" => "Pause", "stop" => "Stop",
        "next" => "Next", "previous" => "Previous", "toggle" => "PlayPause",
        _ => return Err("unknown fixture client action".into()),
    };
    player.call::<_, _, ()>(method, &()).await?;
    Ok(serde_json::json!({"ok":true}))
}

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if let [mode, name, action] = args.as_slice() {
        if mode != "--client" { return Err("invalid fixture mode".into()); }
        println!("{}", client(name, action).await?);
        return Ok(());
    }
    if args == ["--other"] {
        let _other = zbus::connection::Builder::session()?
            .name("org.mpris.MediaPlayer2.OtherFixture")?
            .serve_at("/org/mpris/MediaPlayer2", OtherPlayer)?.build().await?;
        println!("other-ready");
        std::io::stdout().flush()?;
        std::future::pending::<()>().await;
        return Ok(());
    }
    if !args.is_empty() { return Err("invalid fixture mode".into()); }
    let (tx, mut rx) = tokio::sync::mpsc::channel(8);
    let mut metadata = MprisMeta {
        title: "Synthetic visible track 0".into(),
        artists: vec!["Synthetic artist".into()], album: "Synthetic album".into(),
        url_opt: Some(url::Url::parse("file:///synthetic/track0.ogg")?),
        duration_micros: 30_000_000,
        ..Default::default()
    };
    let mut state = MprisState { stopped: false, volume: 0.5, ..Default::default() };
    let server = mpris_backend::start(tx, metadata.clone(), state.clone()).await?;
    println!("{}", server.bus_name());
    std::io::stdout().flush()?;
    let mut input = BufReader::new(tokio::io::stdin()).lines();
    let mut track = 0_u32;
    loop {
        tokio::select! {
            command = rx.recv() => {
                let Some(command) = command else { break };
                match command {
                    PlaybackCommand::Play => { state.paused = false; state.stopped = false; }
                    PlaybackCommand::Pause => state.paused = true,
                    PlaybackCommand::Stop => { state.paused = true; state.stopped = true; state.position_micros = 0; }
                    PlaybackCommand::Toggle => { state.paused = !state.paused; state.stopped = false; }
                    PlaybackCommand::Next => track = track.saturating_add(1),
                    PlaybackCommand::Previous => track = track.saturating_sub(1),
                    PlaybackCommand::Repeat(repeat) => state.repeat_state = repeat,
                    PlaybackCommand::Volume(volume) => state.volume = volume,
                }
                if matches!(command, PlaybackCommand::Next | PlaybackCommand::Previous) {
                    metadata.title = format!("Synthetic visible track {track}");
                    metadata.url_opt = Some(url::Url::parse(&format!("file:///synthetic/track{track}.ogg"))?);
                    mpris_backend::publish(&server, MprisEvent::Meta(metadata.clone())).await?;
                }
                mpris_backend::publish(&server, MprisEvent::State(state.clone())).await?;
            }
            line = input.next_line() => {
                let Some(line) = line? else { break };
                // Simulate a human-visible state change independently of MCP.
                if line == "ui-pause" {
                    state.paused = true;
                    state.stopped = false;
                    mpris_backend::publish(&server, MprisEvent::State(state.clone())).await?;
                } else if let Some(title) = line.strip_prefix("ui-title:") {
                    metadata.title = title.into();
                    mpris_backend::publish(&server, MprisEvent::Meta(metadata.clone())).await?;
                } else { return Err("unknown fixture UI input".into()); }
                println!("updated");
                std::io::stdout().flush()?;
            }
        }
    }
    Ok(())
}
