// SPDX-License-Identifier: GPL-3.0-only

use std::{
    ffi::{OsStr, OsString},
    path::PathBuf,
};

pub(super) fn parse<I>(argv: I, gui_launch: bool) -> Vec<PathBuf>
where
    I: IntoIterator<Item = OsString>,
{
    claw_app_gui_argv::normalize(argv, gui_launch, OsStr::new("--gui"))
        .into_iter()
        .skip(1)
        .map(PathBuf::from)
        .collect()
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/cli.rs"));
}
