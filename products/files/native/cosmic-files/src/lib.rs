// Copyright 2023 System76 <info@system76.com>
// SPDX-License-Identifier: GPL-3.0-only

use cosmic::app::Settings;
use cosmic::iced::Limits;
use std::path::PathBuf;
use std::{env, fs, process};
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;

use crate::app::{App, Flags};
use crate::config::{Config, State};

pub mod app;
mod archive;
pub mod channel;
mod claw_glue;
mod cli;
pub mod clipboard;
pub mod config;
mod context_action;
pub mod dialog;
mod glass;
mod key_bind;
pub(crate) mod large_image;
pub(crate) mod load_image;
mod localize;
mod mcp;
mod menu;
mod mime_app;
pub mod mime_icon;
mod mounter;
mod mouse_area;
pub mod operation;
mod spawn_detached;
pub mod tab;
mod thumbnail_cacher;
mod thumbnailer;
pub(crate) mod trash;
mod zoom;

pub(crate) type FxOrderMap<K, V> = ordermap::OrderMap<K, V, rustc_hash::FxBuildHasher>;

pub(crate) fn err_str<T: ToString>(err: T) -> String {
    err.to_string()
}

pub fn desktop_dir() -> PathBuf {
    if let Some(path) = dirs::desktop_dir() {
        path
    } else {
        let path = home_dir().join("Desktop");
        log::warn!(
            "failed to locate desktop directory, falling back to {}",
            path.display()
        );
        path
    }
}

pub fn home_dir() -> PathBuf {
    if let Some(home) = dirs::home_dir() {
        home
    } else {
        let path = PathBuf::from("/");
        log::warn!(
            "failed to locate home directory, falling back to {}",
            path.display()
        );
        path
    }
}

pub fn is_wayland() -> bool {
    matches!(
        cosmic::app::cosmic::windowing_system(),
        Some(cosmic::app::cosmic::WindowingSystem::Wayland)
    )
}

/// Runs application in desktop mode
#[rustfmt::skip]
pub fn desktop() -> Result<(), Box<dyn std::error::Error>> {
    let log_format = tracing_subscriber::fmt::format()
        .pretty()
        .without_time()
        .with_line_number(true)
        .with_file(true)
        .with_target(false)
        .with_thread_names(true);

    let log_layer = tracing_subscriber::fmt::Layer::default()
        .with_writer(std::io::stderr)
        .event_format(log_format);

    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::from_env("RUST_LOG"))
        .with(log_layer)
        .init();

    localize::localize();

    let (config_handler, config) = Config::load();
    let (state_handler, state) = State::load();

    let mut settings = Settings::default();
    settings = settings.theme(config.app_theme.theme());
    settings = settings.size_limits(Limits::NONE.min_width(360.0).min_height(180.0));
    settings = settings.exit_on_close(false);
    settings = settings.transparent(true);
    settings = settings.blur(true);
    #[cfg(all(feature = "wayland", feature = "desktop-applet"))]
    {
        settings = settings.no_main_window(true);
    }

    let locations = vec![tab::Location::Desktop(desktop_dir(), String::new(), config.desktop)];
    let flags = Flags {
        config_handler,
        config,
        state_handler,
        state,
        mode: app::Mode::Desktop,
        locations,
        uris: Vec::new()
    };
    cosmic::app::run::<App>(settings, flags)?;

    Ok(())
}

/// Runs application with these settings
#[rustfmt::skip]
pub fn main() -> Result<(), Box<dyn std::error::Error>> {
    if std::env::var("COS_MCP_SERVER").as_deref() == Ok("1") {
        return mcp::run().map_err(|e| -> Box<dyn std::error::Error> { e.into() });
    }

    let log_format = tracing_subscriber::fmt::format()
        .pretty()
        .with_line_number(true)
        .with_file(true)
        .with_target(false)
        .with_thread_names(true);

    let log_layer = tracing_subscriber::fmt::Layer::default()
        .with_writer(std::io::stderr)
        .event_format(log_format);

    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::from_default_env())
        .with(log_layer)
        .init();

    localize::localize();

    let (config_handler, config) = Config::load();
    let (state_handler, state) = State::load();

    let cli::Args { daemonize, locations, uris } = cli::parse(
        env::args_os(),
        claw_os_sdk::gui::is_gui_launch(),
        config.show_recents,
        |path| fs::canonicalize(path),
    );

    if daemonize {
        #[cfg(all(unix, not(any(target_os = "macos", target_os = "redox"))))]
        match fork::daemon(true, true) {
            Ok(fork::Fork::Child) => (),
            Ok(fork::Fork::Parent(_child_pid)) => process::exit(0),
            Err(err) => {
                eprintln!("failed to daemonize: {err:?}");
                process::exit(1);
            }
        }
    }

    let mut settings = Settings::default();
    settings = settings.theme(config.app_theme.theme());
    settings = settings.size_limits(Limits::NONE.min_width(360.0).min_height(180.0));
    settings = settings.exit_on_close(false);
    settings = settings.transparent(true);
    settings = settings.blur(true);

    #[cfg(feature = "jemalloc")]
    {
        settings = settings.default_mmap_threshold(None);
    }

    let flags = Flags {
        config_handler,
        config,
        state_handler,
        state,
        mode: app::Mode::App,
        locations,
        uris
    };
    cosmic::app::run::<App>(settings, flags)?;

    Ok(())
}
