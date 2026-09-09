// SPDX-License-Identifier: GPL-3.0-only

use crate::config::RepeatState;

#[derive(Clone, Debug, Default, PartialEq)]
pub struct MprisMeta {
    pub url_opt: Option<url::Url>,
    pub album: String,
    pub album_art_opt: Option<url::Url>,
    pub album_artist: String,
    pub album_year_opt: Option<i32>,
    pub artists: Vec<String>,
    pub title: String,
    pub disc_number: i32,
    pub track_number: i32,
    pub duration_micros: i64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct MprisState {
    pub fullscreen: bool,
    pub position_micros: i64,
    pub paused: bool,
    pub stopped: bool,
    pub volume: f64,
    pub repeat_state: RepeatState,
}

impl Default for MprisState {
    fn default() -> Self {
        Self {
            fullscreen: false,
            position_micros: 0,
            paused: true,
            stopped: true,
            volume: 0.0,
            repeat_state: RepeatState::Disabled,
        }
    }
}

#[derive(Clone, Debug)]
pub enum MprisEvent {
    Meta(MprisMeta),
    State(MprisState),
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum PlaybackCommand {
    Play,
    Pause,
    Stop,
    Toggle,
    Next,
    Previous,
    Repeat(RepeatState),
    Volume(f64),
}
