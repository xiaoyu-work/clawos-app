// SPDX-License-Identifier: GPL-3.0-only

use mpris_server::zbus::{Result, fdo};
use mpris_server::{
    LoopStatus, Metadata, PlaybackRate, PlaybackStatus, PlayerInterface, Property, RootInterface,
    Server, Signal, Time, TrackId, Volume,
};
use std::process;
use tokio::sync::{Mutex, mpsc};

use crate::config::RepeatState;
use crate::playback::{MprisEvent, MprisMeta, MprisState, PlaybackCommand};

impl MprisMeta {
    fn metadata(&self) -> Metadata {
        let mut meta = Metadata::builder()
            //TODO: better track id
            .trackid(
                mpris_server::TrackId::try_from(format!(
                    "/com/clawos/Player/pid{}/TrackList/0",
                    process::id()
                ))
                .unwrap(),
            )
            .length(Time::from_micros(self.duration_micros));
        if let Some(url) = &self.url_opt {
            meta = meta.url(url.clone());
        }
        if !self.album.is_empty() {
            meta = meta.album(&self.album);
        }
        if let Some(album_art) = &self.album_art_opt {
            meta = meta.art_url(album_art.clone());
        }
        if !self.artists.is_empty() {
            meta = meta.artist(&self.artists);
        }
        //TODO: content_created
        if !self.title.is_empty() {
            meta = meta.title(&self.title);
        }
        //TODO .disc_number(self.disc_number)
        if self.track_number > 0 {
            meta = meta.track_number(self.track_number);
        }
        //TODO: track count?
        //TODO: more keys, see https://docs.rs/mpris-server/0.8.1/mpris_server/builder/struct.MetadataBuilder.html
        meta.build()
    }
}

impl MprisState {
    fn playback_status(&self) -> PlaybackStatus {
        if self.stopped {
            PlaybackStatus::Stopped
        } else if self.paused {
            PlaybackStatus::Paused
        } else {
            PlaybackStatus::Playing
        }
    }

    fn loop_status(&self) -> LoopStatus {
        match self.repeat_state {
            RepeatState::Disabled => LoopStatus::None,
            RepeatState::Track => LoopStatus::Track,
        }
    }
}

pub struct Player {
    command_tx: mpsc::Sender<PlaybackCommand>,
    meta: Mutex<MprisMeta>,
    state: Mutex<MprisState>,
}

impl Player {
    async fn message(&self, message: PlaybackCommand) -> fdo::Result<()> {
        self.command_tx
            .send(message)
            .await
            .map_err(|err| fdo::Error::Failed(err.to_string()))
    }
}

impl RootInterface for Player {
    async fn raise(&self) -> fdo::Result<()> {
        log::info!("Raise");
        Ok(())
    }

    async fn quit(&self) -> fdo::Result<()> {
        log::info!("Quit");
        Ok(())
    }

    async fn can_quit(&self) -> fdo::Result<bool> {
        log::info!("CanQuit");
        Ok(false)
    }

    async fn fullscreen(&self) -> fdo::Result<bool> {
        log::info!("Fullscreen");
        let state = self.state.lock().await;
        Ok(state.fullscreen)
    }

    async fn set_fullscreen(&self, fullscreen: bool) -> Result<()> {
        log::info!("SetFullscreen({})", fullscreen);
        Ok(())
    }

    async fn can_set_fullscreen(&self) -> fdo::Result<bool> {
        log::info!("CanSetFullscreen");
        Ok(false)
    }

    async fn can_raise(&self) -> fdo::Result<bool> {
        log::info!("CanRaise");
        Ok(false)
    }

    async fn has_track_list(&self) -> fdo::Result<bool> {
        log::info!("HasTrackList");
        Ok(false)
    }

    async fn identity(&self) -> fdo::Result<String> {
        log::info!("Identity");
        Ok("Media Player".to_string())
    }

    async fn desktop_entry(&self) -> fdo::Result<String> {
        log::info!("DesktopEntry");
        Ok("com.clawos.Player".to_string())
    }

    async fn supported_uri_schemes(&self) -> fdo::Result<Vec<String>> {
        log::info!("SupportedUriSchemes");
        Ok(vec![])
    }

    async fn supported_mime_types(&self) -> fdo::Result<Vec<String>> {
        log::info!("SupportedMimeTypes");
        Ok(vec![])
    }
}

impl PlayerInterface for Player {
    async fn next(&self) -> fdo::Result<()> {
        log::info!("Next");
        self.message(PlaybackCommand::Next).await
    }

    async fn previous(&self) -> fdo::Result<()> {
        log::info!("Previous");
        self.message(PlaybackCommand::Previous).await
    }

    async fn pause(&self) -> fdo::Result<()> {
        log::info!("Pause");
        self.message(PlaybackCommand::Pause).await
    }

    async fn play_pause(&self) -> fdo::Result<()> {
        log::info!("PlayPause");
        self.message(PlaybackCommand::Toggle).await
    }

    async fn stop(&self) -> fdo::Result<()> {
        log::info!("Stop");
        self.message(PlaybackCommand::Stop).await
    }

    async fn play(&self) -> fdo::Result<()> {
        log::info!("Play");
        self.message(PlaybackCommand::Play).await
    }

    async fn seek(&self, offset: Time) -> fdo::Result<()> {
        log::info!("Seek({:?})", offset);
        Ok(())
    }

    async fn set_position(&self, track_id: TrackId, position: Time) -> fdo::Result<()> {
        log::info!("SetPosition({}, {:?})", track_id, position);
        Ok(())
    }

    async fn open_uri(&self, uri: String) -> fdo::Result<()> {
        log::info!("OpenUri({})", uri);
        Ok(())
    }

    async fn playback_status(&self) -> fdo::Result<PlaybackStatus> {
        log::info!("PlaybackStatus");
        let state = self.state.lock().await;
        Ok(state.playback_status())
    }

    async fn loop_status(&self) -> fdo::Result<LoopStatus> {
        log::info!("LoopStatus");
        let state = self.state.lock().await;
        Ok(state.loop_status())
    }

    async fn set_loop_status(&self, loop_status: LoopStatus) -> Result<()> {
        log::info!("SetLoopStatus({})", loop_status);
        let repeat_state = match loop_status {
            LoopStatus::None => RepeatState::Disabled,
            LoopStatus::Track | LoopStatus::Playlist => RepeatState::Track,
        };
        self.message(PlaybackCommand::Repeat(repeat_state)).await?;
        Ok(())
    }

    async fn rate(&self) -> fdo::Result<PlaybackRate> {
        log::info!("Rate");
        Ok(1.0)
    }

    async fn set_rate(&self, rate: PlaybackRate) -> Result<()> {
        log::info!("SetRate({})", rate);
        Ok(())
    }

    async fn shuffle(&self) -> fdo::Result<bool> {
        log::info!("Shuffle");
        Ok(false)
    }

    async fn set_shuffle(&self, shuffle: bool) -> Result<()> {
        log::info!("SetShuffle({})", shuffle);
        Ok(())
    }

    async fn metadata(&self) -> fdo::Result<Metadata> {
        log::info!("Metadata");
        let meta = self.meta.lock().await;
        Ok(meta.metadata())
    }

    async fn volume(&self) -> fdo::Result<Volume> {
        log::info!("Volume");
        let state = self.state.lock().await;
        Ok(state.volume)
    }

    async fn set_volume(&self, volume: Volume) -> Result<()> {
        log::info!("SetVolume({})", volume);
        self.message(PlaybackCommand::Volume(volume)).await?;
        Ok(())
    }

    async fn position(&self) -> fdo::Result<Time> {
        log::info!("Position");
        let state = self.state.lock().await;
        Ok(Time::from_micros(state.position_micros))
    }

    async fn minimum_rate(&self) -> fdo::Result<PlaybackRate> {
        log::info!("MinimumRate");
        Ok(1.0)
    }

    async fn maximum_rate(&self) -> fdo::Result<PlaybackRate> {
        log::info!("MaximumRate");
        Ok(1.0)
    }

    async fn can_go_next(&self) -> fdo::Result<bool> {
        log::info!("CanGoNext");
        Ok(true)
    }

    async fn can_go_previous(&self) -> fdo::Result<bool> {
        log::info!("CanGoPrevious");
        Ok(true)
    }

    async fn can_play(&self) -> fdo::Result<bool> {
        log::info!("CanPlay");
        Ok(true)
    }

    async fn can_pause(&self) -> fdo::Result<bool> {
        log::info!("CanPause");
        Ok(true)
    }

    async fn can_seek(&self) -> fdo::Result<bool> {
        log::info!("CanSeek");
        Ok(false)
    }

    async fn can_control(&self) -> fdo::Result<bool> {
        log::info!("CanControl");
        Ok(true)
    }
}

/*TODO: implement mpris tracklist
impl TrackListInterface for Player {
    async fn get_tracks_metadata(&self, track_ids: Vec<TrackId>) -> fdo::Result<Vec<Metadata>> {
        log::info!("GetTracksMetadata({:?})", track_ids);
        Ok(vec![])
    }

    async fn add_track(
        &self,
        uri: Uri,
        after_track: TrackId,
        set_as_current: bool,
    ) -> fdo::Result<()> {
        log::info!("AddTrack({}, {}, {})", uri, after_track, set_as_current);
        Ok(())
    }

    async fn remove_track(&self, track_id: TrackId) -> fdo::Result<()> {
        log::info!("RemoveTrack({})", track_id);
        Ok(())
    }

    async fn go_to(&self, track_id: TrackId) -> fdo::Result<()> {
        log::info!("GoTo({})", track_id);
        Ok(())
    }

    async fn tracks(&self) -> fdo::Result<Vec<TrackId>> {
        log::info!("Tracks");
        Ok(vec![])
    }

    async fn can_edit_tracks(&self) -> fdo::Result<bool> {
        log::info!("CanEditTracks");
        Ok(false)
    }
}
*/

/*TODO: implement mpris playlists
impl PlaylistsInterface for Player {
    async fn activate_playlist(&self, playlist_id: PlaylistId) -> fdo::Result<()> {
        log::info!("ActivatePlaylist({})", playlist_id);
        Ok(())
    }

    async fn get_playlists(
        &self,
        index: u32,
        max_count: u32,
        order: PlaylistOrdering,
        reverse_order: bool,
    ) -> fdo::Result<Vec<Playlist>> {
        log::info!(
            "GetPlaylists({}, {}, {}, {})",
            index, max_count, order, reverse_order
        );
        Ok(vec![])
    }

    async fn playlist_count(&self) -> fdo::Result<u32> {
        log::info!("PlaylistCount");
        Ok(0)
    }

    async fn orderings(&self) -> fdo::Result<Vec<PlaylistOrdering>> {
        log::info!("Orderings");
        Ok(vec![])
    }

    async fn active_playlist(&self) -> fdo::Result<Option<Playlist>> {
        log::info!("ActivePlaylist");
        Ok(None)
    }
}
*/

pub async fn start(
    command_tx: mpsc::Sender<PlaybackCommand>,
    meta: MprisMeta,
    state: MprisState,
) -> Result<Server<Player>> {
    Server::new(
        &format!("com.clawos.Player.pid{}", process::id()),
        Player { command_tx, meta: Mutex::new(meta), state: Mutex::new(state) },
    ).await
}

pub async fn publish(server: &Server<Player>, event: MprisEvent) -> Result<()> {
    let mut props = Vec::new();
    let mut sigs = Vec::new();
    match event {
        MprisEvent::Meta(new) => {
            let mut old = server.imp().meta.lock().await;
            let new_metadata = new.metadata();
            if new_metadata != old.metadata() {
                props.push(Property::Metadata(new_metadata));
            }
            *old = new;
        }
        MprisEvent::State(new) => {
            let mut old = server.imp().state.lock().await;
            if new.fullscreen != old.fullscreen {
                props.push(Property::Fullscreen(new.fullscreen));
            }
            let new_playback_status = new.playback_status();
            if new_playback_status != old.playback_status() {
                props.push(Property::PlaybackStatus(new_playback_status));
            }
            if new.volume != old.volume {
                props.push(Property::Volume(new.volume));
            }
            if new.position_micros != old.position_micros {
                sigs.push(Signal::Seeked { position: Time::from_micros(new.position_micros) });
            }
            let new_loop_status = new.loop_status();
            if new_loop_status != old.loop_status() {
                props.push(Property::LoopStatus(new_loop_status));
            }
            *old = new;
        }
    }
    if !props.is_empty() {
        server.properties_changed(props).await?;
    }
    for signal in sigs {
        server.emit(signal).await?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/mpris_backend.rs"));
}
