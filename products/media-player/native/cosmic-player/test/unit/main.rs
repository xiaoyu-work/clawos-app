use super::*;

#[test]
fn every_native_mpris_command_uses_the_existing_ui_message() {
    assert!(matches!(Message::from(PlaybackCommand::Play), Message::Play));
    assert!(matches!(Message::from(PlaybackCommand::Pause), Message::Pause));
    assert!(matches!(Message::from(PlaybackCommand::Stop), Message::Stop));
    assert!(matches!(Message::from(PlaybackCommand::Toggle), Message::PlayPause));
    assert!(matches!(Message::from(PlaybackCommand::Next), Message::PlayNext));
    assert!(matches!(Message::from(PlaybackCommand::Previous), Message::PlayPrev));
    assert!(matches!(Message::from(PlaybackCommand::Repeat(RepeatState::Track)), Message::RepeatToggled(RepeatState::Track)));
    assert!(matches!(Message::from(PlaybackCommand::Volume(0.5)), Message::AudioVolume(0.5)));
}
