// SPDX-License-Identifier: GPL-3.0-only

use super::*;
use std::ffi::{OsStr, OsString};

fn launch_args<I, T>(argv: I, gui: bool) -> Result<Args, clap::Error>
where
    I: IntoIterator<Item = T>,
    T: Into<OsString>,
{
    Args::try_parse_from(claw_app_gui_argv::normalize(
        argv.into_iter().map(Into::into),
        gui,
        OsStr::new("--gui"),
    ))
}

fn result_text(value: Result<Args, clap::Error>) -> String {
    match value {
        Ok(args) => format!("{args:?}"),
        Err(error) => format!("{}:{:?}:{error}", error.exit_code(), error.kind()),
    }
}

#[test]
fn native_gui_argv_preserves_the_actual_settings_parser() {
    let cases: &[&[&str]] = &[
        &[],
        &["appearance"],
        &["appearance", "import", "theme with spaces.ron"],
        &["appearance", "export", "--", "--gui"],
        &["appearance", "import", "file:///theme.ron"],
        &["appearance", "import"],
        &["appearance", "import", "one.ron", "two.ron"],
        &["appearance", "--help"],
        &["--help"],
        &["--version"],
        &["--unknown"],
        &["--", "--gui"],
    ];
    for arguments in cases {
        let direct = std::iter::once("cosmic-settings").chain(arguments.iter().copied());
        let gui = ["cosmic-settings", "--gui"]
            .into_iter()
            .chain(arguments.iter().copied());
        assert_eq!(
            result_text(launch_args(direct, false)),
            result_text(launch_args(gui, true)),
            "{arguments:?}",
        );
    }
}

#[test]
fn native_gui_argv_consumes_only_the_host_selector() {
    let direct = launch_args(["cosmic-settings", "--gui"], false).unwrap_err();
    assert_eq!(direct.kind(), clap::error::ErrorKind::UnknownArgument);
    let repeated = launch_args(["cosmic-settings", "--gui", "--gui"], true).unwrap_err();
    assert_eq!(direct.to_string(), repeated.to_string());
    assert!(launch_args(["cosmic-settings"], true).is_ok());
}

#[test]
fn native_gui_argv_preserves_end_of_options_theme_paths() {
    let args = launch_args(
        [
            "cosmic-settings",
            "--gui",
            "appearance",
            "import",
            "--",
            "--gui",
        ],
        true,
    )
    .unwrap();
    let Some(PageCommands::Appearance {
        command: Some(AppearanceCommands::Import { path }),
    }) = args.sub_command
    else {
        panic!("appearance import was not preserved");
    };
    assert_eq!(path, PathBuf::from("--gui"));
}

#[test]
fn native_gui_argv_retains_early_help_and_version() {
    for (flag, kind) in [
        ("--help", clap::error::ErrorKind::DisplayHelp),
        ("--version", clap::error::ErrorKind::DisplayVersion),
    ] {
        let error = launch_args(["cosmic-settings", "--gui", flag], true).unwrap_err();
        assert_eq!(error.kind(), kind);
        assert_eq!(error.exit_code(), 0);
    }
}

#[cfg(unix)]
#[test]
fn native_gui_argv_preserves_non_utf8_theme_paths() {
    use std::os::unix::ffi::OsStringExt;

    let path = OsString::from_vec(b"theme-\xff.ron".to_vec());
    let args = launch_args(
        [
            OsString::from("cosmic-settings"),
            OsString::from("--gui"),
            OsString::from("appearance"),
            OsString::from("export"),
            path.clone(),
        ],
        true,
    )
    .unwrap();
    let Some(PageCommands::Appearance {
        command: Some(AppearanceCommands::Export { path: parsed }),
    }) = args.sub_command
    else {
        panic!("appearance export was not preserved");
    };
    assert_eq!(parsed, PathBuf::from(path));
}
