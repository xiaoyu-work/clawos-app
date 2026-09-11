// SPDX-License-Identifier: GPL-3.0-only

use std::{
    ffi::{OsStr, OsString},
    io,
    path::{Path, PathBuf},
};

use crate::tab::Location;

#[derive(Debug, PartialEq)]
pub(super) struct Args {
    pub(super) daemonize: bool,
    pub(super) locations: Vec<Location>,
    pub(super) uris: Vec<url::Url>,
}

pub(super) fn parse<I>(
    argv: I,
    gui_launch: bool,
    show_recents: bool,
    mut canonicalize: impl FnMut(&Path) -> io::Result<PathBuf>,
) -> Args
where
    I: IntoIterator<Item = OsString>,
{
    let mut daemonize = true;
    let mut locations = Vec::new();
    let mut uris = Vec::new();
    for arg in claw_app_gui_argv::normalize(argv, gui_launch, OsStr::new("--gui"))
        .into_iter()
        .skip(1)
    {
        let location = if arg == "--no-daemon" {
            daemonize = false;
            continue;
        } else if arg == "--trash" {
            Location::Trash
        } else if arg == "--recents" {
            if show_recents {
                Location::Recents
            } else {
                log::warn!("recents feature is disabled in config");
                continue;
            }
        } else if arg == "--network" {
            Location::Network("network:///".to_string(), crate::fl!("networks"), None)
        } else {
            let path = match arg.to_str().and_then(|arg| url::Url::parse(arg).ok()) {
                Some(url) if url.scheme() == "file" => {
                    if let Ok(path) = url.to_file_path() {
                        path
                    } else {
                        log::warn!("invalid argument {arg:?}");
                        continue;
                    }
                }
                Some(url) => {
                    uris.push(url);
                    continue;
                }
                None => PathBuf::from(arg),
            };
            match canonicalize(&path) {
                Ok(absolute) => Location::Path(absolute),
                Err(err) => {
                    log::warn!("failed to canonicalize {}: {}", path.display(), err);
                    continue;
                }
            }
        };
        locations.push(location);
    }
    Args {
        daemonize,
        locations,
        uris,
    }
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/cli.rs"));
}
