// SPDX-License-Identifier: GPL-3.0-only

use clap_lex::RawArgs;
use std::{
    ffi::{OsStr, OsString},
    path::PathBuf,
};

#[derive(Debug, Eq, PartialEq)]
pub(super) struct Args {
    pub(super) shell_program_opt: Option<String>,
    pub(super) shell_args: Vec<String>,
    pub(super) daemonize: bool,
    pub(super) working_directory: Option<PathBuf>,
}

#[derive(Debug, Eq, PartialEq)]
pub(super) enum Outcome {
    Run(Args),
    Help,
    Version,
}

pub(super) fn parse<I>(argv: I, gui_launch: bool) -> Result<Outcome, String>
where
    I: IntoIterator<Item = OsString>,
{
    let raw_args = RawArgs::new(claw_app_gui_argv::normalize(
        argv,
        gui_launch,
        OsStr::new("--gui"),
    ));
    let mut cursor = raw_args.cursor();
    let mut shell_program_opt = None;
    let mut shell_args = Vec::new();
    let mut daemonize = true;
    let mut working_directory = None;

    // Keep the native parser's argv0 handling and command delimiters.
    while let Some(arg) = raw_args.next_os(&mut cursor) {
        match arg.to_str() {
            Some("--help") | Some("-h") => return Ok(Outcome::Help),
            Some("--version") | Some("-V") => return Ok(Outcome::Version),
            Some(arg_str @ "--working-directory") | Some(arg_str @ "-w") => {
                if let Some(dir_arg) = raw_args.next_os(&mut cursor) {
                    working_directory = Some(PathBuf::from(dir_arg));
                } else {
                    return Err(format!("Missing argument for {arg_str}"));
                }
            }
            Some("--no-daemon") => daemonize = false,
            Some("-e") | Some("--command") | Some("--") => break,
            _ => log::warn!("ignored argument {:?}", arg),
        }
    }
    while let Some(arg) = raw_args.next_os(&mut cursor) {
        if shell_program_opt.is_some() {
            shell_args.push(arg.to_string_lossy().to_string());
        } else {
            shell_program_opt = Some(arg.to_string_lossy().to_string());
        }
    }

    Ok(Outcome::Run(Args {
        shell_program_opt,
        shell_args,
        daemonize,
        working_directory,
    }))
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/cli.rs"));
}
