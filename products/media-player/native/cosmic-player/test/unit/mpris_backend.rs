use super::*;

#[tokio::test]
async fn native_mpris_controls_reach_the_ui_channel_including_stop() {
    let (command_tx, mut commands) = mpsc::channel(8);
    let player = Player {
        command_tx, meta: Mutex::new(MprisMeta::default()), state: Mutex::new(MprisState::default()),
    };
    player.play().await.unwrap();
    player.pause().await.unwrap();
    player.stop().await.unwrap();
    player.next().await.unwrap();
    player.previous().await.unwrap();
    player.play_pause().await.unwrap();
    for command in [PlaybackCommand::Play, PlaybackCommand::Pause, PlaybackCommand::Stop,
        PlaybackCommand::Next, PlaybackCommand::Previous, PlaybackCommand::Toggle] {
        assert_eq!(commands.recv().await, Some(command));
    }
    assert!(commands.try_recv().is_err());
    assert_eq!(player.desktop_entry().await.unwrap(), "com.clawos.Player");
    drop(commands);
    assert!(player.play().await.is_err(), "a closed UI is not a successful playback");
}

#[test]
fn native_playback_status_and_metadata_are_derived_from_ui_state() {
    let mut state = MprisState::default();
    assert_eq!(state.playback_status(), PlaybackStatus::Stopped);
    state.stopped = false;
    assert_eq!(state.playback_status(), PlaybackStatus::Paused);
    state.paused = false;
    assert_eq!(state.playback_status(), PlaybackStatus::Playing);
    state.stopped = true;
    assert_eq!(state.playback_status(), PlaybackStatus::Stopped);
    let meta = MprisMeta {
        title: "Native UI title".into(), artists: vec!["Synthetic artist".into()],
        album: "Synthetic album".into(), duration_micros: 1_234_567,
        url_opt: Some(url::Url::parse("file:///synthetic/song.ogg").unwrap()),
        ..Default::default()
    }.metadata();
    assert_eq!(meta.title(), Some("Native UI title"));
    assert_eq!(meta.album(), Some("Synthetic album"));
    assert_eq!(meta.length(), Some(Time::from_micros(1_234_567)));
}
