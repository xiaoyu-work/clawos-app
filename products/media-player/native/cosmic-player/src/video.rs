use iced_video_player::gst::prelude::*;
use iced_video_player::{Video, gst, gst_app, gst_pbutils};

use cosmic::action;
use cosmic::app::Task;
use std::ops::{Deref, DerefMut};

pub struct NativeVideo {
    video: Video,
    _audio: Option<super::audio::Output>,
}

impl Deref for NativeVideo {
    type Target = Video;
    fn deref(&self) -> &Video { &self.video }
}

impl DerefMut for NativeVideo {
    fn deref_mut(&mut self) -> &mut Video { &mut self.video }
}

#[derive(Debug, Default)]
pub struct VideoSettings {
    pub mute: bool,
}

pub fn new_video(
    url: &url::Url,
    settings: VideoSettings,
) -> Result<NativeVideo, cosmic::Task<cosmic::Action<super::Message>>> {
    //TODO: this code came from iced_video_player::Video::new and has been modified to stop the pipeline on error
    //TODO: remove unwraps and enable playback of files with only audio.
    gst::init().unwrap();

    let audio = if claw_os_sdk::gui::is_gui_launch() && !settings.mute {
        match super::audio::Output::open() {
            Ok(output) => Some(output),
            Err(error) => {
                log::error!("{error}");
                return Err(Task::none());
            }
        }
    } else { None };
    let sink = if settings.mute {
        " audio-sink=\"fakesink sync=false\"".into()
    } else {
        audio.as_ref().map(|output| format!(
            " audio-sink=\"audioconvert ! audioresample ! audio/x-raw,format=S16LE,channels=2,rate=48000,layout=interleaved ! fdsink fd={} sync=true\"",
            output.descriptor(),
        )).unwrap_or_default()
    };
    let pipeline = format!(
        "playbin uri=\"{}\"{}{} video-sink=\"videoscale ! videoconvert ! videoflip method=automatic ! appsink name=iced_video drop=true caps=video/x-raw,format=NV12,pixel-aspect-ratio=1/1\"",
        url.as_str(),
        if settings.mute { " mute=true" } else { "" },
        sink,
    );
    let pipeline = gst::parse::launch(pipeline.as_ref())
        .unwrap()
        .downcast::<gst::Pipeline>()
        .map_err(|_| iced_video_player::Error::Cast)
        .unwrap();
    pipeline.connect("element-setup", false, |vals| {
        let Ok(elem) = vals[1].get::<gst::Element>() else {
            return None;
        };
        if let Some(factory) = elem.factory()
            && factory.name() == "souphttpsrc"
        {
            elem.set_property(
                "user-agent",
                "Mozilla/5.0 (X11; Linux x86_64; rv:142.0) Gecko/20100101 Firefox/142.0",
            );
        }
        None
    });
    let video_sink: gst::Element = pipeline.property("video-sink");
    let pad = video_sink.pads().first().cloned().unwrap();
    let pad = pad.dynamic_cast::<gst::GhostPad>().unwrap();
    let bin = pad
        .parent_element()
        .unwrap()
        .downcast::<gst::Bin>()
        .unwrap();
    let video_sink = bin.by_name("iced_video").unwrap();
    let video_sink = video_sink.downcast::<gst_app::AppSink>().unwrap();

    match Video::from_gst_pipeline(pipeline.clone(), video_sink, None) {
        Ok(video) => Ok(NativeVideo { video, _audio:audio }),
        Err(err) => {
            log::warn!("failed to open {}: {err}", url);
            // Handle codecs required before the file can play
            let mut commands = Vec::new();
            while let Some(msg) = pipeline
                .bus()
                .unwrap()
                .pop_filtered(&[gst::MessageType::Element])
            {
                if let gst::MessageView::Element(element) = msg.view()
                    && gst_pbutils::MissingPluginMessage::is(element)
                {
                    commands.push(Task::perform(
                        async { action::app(super::Message::MissingPlugin(msg)) },
                        |x| x,
                    ));
                    // Do one codec install at a time
                    break;
                }
            }
            pipeline.set_state(gst::State::Null).unwrap();
            Err(Task::batch(commands))
        }
    }
}
