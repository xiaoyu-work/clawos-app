// Copyright 2023 System76 <info@system76.com>
// SPDX-License-Identifier: GPL-3.0-only

use clap::Parser;
use std::ffi::{OsStr, OsString};

#[derive(Debug, Default, Parser)]
pub(crate) struct Cli {
    pub(crate) subcommand_opt: Option<String>,
    //TODO: should these extra gst-install-plugins-helper arguments actually be handled?
    #[arg(long)]
    pub(crate) transient_for: Option<String>,
    #[arg(long)]
    pub(crate) interaction: Option<String>,
    #[arg(long)]
    pub(crate) desktop_id: Option<String>,
    #[arg(long)]
    pub(crate) startup_notification_id: Option<String>,
}

pub(crate) fn parse() -> Cli {
    parse_from(std::env::args_os(), claw_os_sdk::gui::is_gui_launch())
        .unwrap_or_else(|error| error.exit())
}

fn parse_from<I>(argv: I, gui_launch: bool) -> Result<Cli, clap::Error>
where
    I: IntoIterator<Item = OsString>,
{
    Cli::try_parse_from(claw_app_gui_argv::normalize(
        argv,
        gui_launch,
        OsStr::new("--gui"),
    ))
}

#[cfg(test)]
mod tests {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/unit/argparse.rs"
    ));
}
