use clap::Parser;
use serde::{Deserialize, Serialize};
use std::ffi::{OsStr, OsString};
use std::fmt::Display;
use std::str::FromStr;

#[derive(Parser, Debug, Serialize, Deserialize, Clone)]
#[command(author, version, about, long_about = None)]
#[command(propagate_version = true)]
pub struct Args {
    #[clap(subcommand)]
    pub subcommand: Option<LauncherTasks>,
}

#[derive(Debug, Serialize, Deserialize, Clone, clap::Subcommand)]
pub enum LauncherTasks {
    #[clap(about = "Toggle the launcher and switch to the alt-tab view")]
    AltTab,
    #[clap(about = "Toggle the launcher and switch to the alt-tab view")]
    ShiftAltTab,
    #[clap(about = "Start the launcher with an input")]
    Input { input: Option<String> },
    #[clap(about = "Close the launcher if open")]
    Close,
}

impl Display for LauncherTasks {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", serde_json::ser::to_string(self).unwrap())
    }
}

impl FromStr for LauncherTasks {
    type Err = serde_json::Error;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        serde_json::de::from_str(s)
    }
}

pub(crate) fn parse() -> Args {
    parse_from(std::env::args_os(), claw_os_sdk::gui::is_gui_launch())
        .unwrap_or_else(|error| error.exit())
}

fn parse_from<I>(argv: I, gui_launch: bool) -> Result<Args, clap::Error>
where
    I: IntoIterator<Item = OsString>,
{
    Args::try_parse_from(claw_app_gui_argv::normalize(
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
