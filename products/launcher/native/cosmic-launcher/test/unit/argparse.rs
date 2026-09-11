use super::*;
use clap::error::ErrorKind;

fn parse_argv(argv: &[&str], gui_launch: bool) -> Result<Args, clap::Error> {
    parse_from(argv.iter().map(OsString::from), gui_launch)
}

#[test]
fn gui_selector_is_only_accepted_as_the_first_gui_argument() {
    for gui_launch in [false, true] {
        assert!(
            parse_argv(&["launcher"], gui_launch)
                .unwrap()
                .subcommand
                .is_none()
        );
        assert!(
            parse_argv(&["--gui"], gui_launch)
                .unwrap()
                .subcommand
                .is_none()
        );
        for argv in [
            vec!["launcher", "--gui=value"],
            vec!["launcher", "close", "--gui"],
            vec!["launcher", "input", "--gui"],
        ] {
            assert_eq!(parse_argv(&argv, gui_launch).unwrap_err().exit_code(), 2);
        }
    }
    assert!(
        parse_argv(&["launcher", "--gui"], true)
            .unwrap()
            .subcommand
            .is_none()
    );
    let direct = parse_argv(&["launcher", "--gui"], false).unwrap_err();
    assert_eq!(direct.kind(), ErrorKind::UnknownArgument);
    assert_eq!(direct.exit_code(), 2);
    assert_eq!(
        parse_argv(&["launcher", "--gui", "--gui"], true)
            .unwrap_err()
            .exit_code(),
        2
    );
}

#[test]
fn ordinary_subcommands_and_input_values_are_unchanged() {
    for gui_launch in [false, true] {
        for command in ["alt-tab", "shift-alt-tab", "close", "input"] {
            let direct = parse_argv(&["launcher", command], gui_launch).unwrap();
            let hosted = parse_argv(&["launcher", "--gui", command], true).unwrap();
            assert_eq!(
                serde_json::to_value(&direct).unwrap(),
                serde_json::to_value(&hosted).unwrap()
            );
            let task = direct.subcommand.unwrap();
            let restored = LauncherTasks::from_str(&task.to_string()).unwrap();
            assert_eq!(
                serde_json::to_value(task).unwrap(),
                serde_json::to_value(restored).unwrap()
            );
        }
        for value in [
            "two words",
            "https://example.test/media?name=--gui",
            "/fixture/文 件",
        ] {
            for argv in [
                vec!["launcher", "input", value],
                vec!["launcher", "input", "--", value],
            ] {
                assert!(matches!(
                    parse_argv(&argv, gui_launch).unwrap().subcommand,
                    Some(LauncherTasks::Input { input: Some(input) }) if input == value
                ));
            }
        }
    }
}

#[test]
fn input_end_of_options_preserves_a_literal_gui_value() {
    for gui_launch in [false, true] {
        assert!(matches!(
            parse_argv(&["launcher", "input", "--", "--gui"], gui_launch).unwrap().subcommand,
            Some(LauncherTasks::Input { input: Some(input) }) if input == "--gui"
        ));
    }
    assert!(matches!(
        parse_argv(&["launcher", "--gui", "input", "--", "--gui"], true).unwrap().subcommand,
        Some(LauncherTasks::Input { input: Some(input) }) if input == "--gui"
    ));
}

#[test]
fn help_version_and_parser_errors_keep_their_exit_codes() {
    for (flag, kind) in [
        ("-h", ErrorKind::DisplayHelp),
        ("--help", ErrorKind::DisplayHelp),
        ("help", ErrorKind::DisplayHelp),
        ("-V", ErrorKind::DisplayVersion),
        ("--version", ErrorKind::DisplayVersion),
    ] {
        for gui_launch in [false, true] {
            let error = parse_argv(&["launcher", flag], gui_launch).unwrap_err();
            assert_eq!(error.kind(), kind);
            assert_eq!(error.exit_code(), 0);
            assert!(!error.use_stderr());
        }
        let error = parse_argv(&["launcher", "--gui", flag], true).unwrap_err();
        assert_eq!(error.kind(), kind);
        assert_eq!(error.exit_code(), 0);
        assert!(!error.to_string().contains("--gui"));
    }
    for gui_launch in [false, true] {
        for argv in [
            vec!["launcher", "--unknown"],
            vec!["launcher", "unknown-command"],
            vec!["launcher", "input", "one", "two"],
        ] {
            assert_eq!(parse_argv(&argv, gui_launch).unwrap_err().exit_code(), 2);
        }
        let version = parse_argv(&["launcher", "input", "--version"], gui_launch).unwrap_err();
        assert_eq!(version.kind(), ErrorKind::DisplayVersion);
        assert_eq!(version.exit_code(), 0);
    }
    let help = parse_argv(&["renamed-launcher", "--gui", "--help"], true).unwrap_err();
    assert!(help.to_string().contains("Usage: renamed-launcher"));
}

#[cfg(unix)]
#[test]
fn os_arguments_are_not_lossily_converted_before_clap() {
    use std::os::unix::ffi::OsStringExt;

    let argv0 = OsString::from_vec(b"launcher-\xff".to_vec());
    let args = parse_from([argv0.clone(), "--gui".into(), "close".into()], true).unwrap();
    assert!(matches!(args.subcommand, Some(LauncherTasks::Close)));
    for gui_launch in [false, true] {
        let error = parse_from(
            [
                argv0.clone(),
                "input".into(),
                OsString::from_vec(b"value-\xff".to_vec()),
            ],
            gui_launch,
        )
        .unwrap_err();
        assert_eq!(error.kind(), ErrorKind::InvalidUtf8);
        assert_eq!(error.exit_code(), 2);
    }
}
