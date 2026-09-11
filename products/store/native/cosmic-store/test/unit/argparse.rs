use super::*;
use clap::error::ErrorKind;

fn parse_argv(argv: &[&str], gui_launch: bool) -> Result<Cli, clap::Error> {
    parse_from(argv.iter().map(OsString::from), gui_launch)
}

#[test]
fn only_one_leading_gui_selector_is_removed() {
    for gui_launch in [false, true] {
        assert!(
            parse_argv(&["store"], gui_launch)
                .unwrap()
                .subcommand_opt
                .is_none()
        );
        assert!(
            parse_argv(&["--gui"], gui_launch)
                .unwrap()
                .subcommand_opt
                .is_none()
        );
        for argv in [
            vec!["store", "--gui=value"],
            vec!["store", "search", "--gui"],
        ] {
            assert_eq!(parse_argv(&argv, gui_launch).unwrap_err().exit_code(), 2);
        }
    }
    assert!(
        parse_argv(&["store", "--gui"], true)
            .unwrap()
            .subcommand_opt
            .is_none()
    );
    let direct = parse_argv(&["store", "--gui"], false).unwrap_err();
    assert_eq!(direct.kind(), ErrorKind::UnknownArgument);
    assert_eq!(direct.exit_code(), 2);
    assert_eq!(
        parse_argv(&["store", "--gui", "--gui"], true)
            .unwrap_err()
            .exit_code(),
        2
    );
}

#[test]
fn search_uri_and_codec_arguments_keep_their_original_boundaries() {
    let codec = "gstreamer|1.0|cosmic-player|H.264 (Main Profile) decoder|decoder-video/x-h264, level=(string)3.1, profile=(string)main";
    for query in [
        "two words",
        "文 件",
        "appstream://org.example.App",
        "file:///fixture/app.flatpakref",
        codec,
    ] {
        for gui_launch in [false, true] {
            assert_eq!(
                parse_argv(&["store", query], gui_launch)
                    .unwrap()
                    .subcommand_opt
                    .as_deref(),
                Some(query)
            );
        }
        let cli = parse_argv(
            &[
                "store",
                "--gui",
                "--transient-for",
                "42",
                "--interaction=full",
                query,
                "--desktop-id",
                "org.example.App",
                "--startup-notification-id=--gui",
            ],
            true,
        )
        .unwrap();
        assert_eq!(cli.subcommand_opt.as_deref(), Some(query));
        assert_eq!(cli.transient_for.as_deref(), Some("42"));
        assert_eq!(cli.interaction.as_deref(), Some("full"));
        assert_eq!(cli.desktop_id.as_deref(), Some("org.example.App"));
        assert_eq!(cli.startup_notification_id.as_deref(), Some("--gui"));
    }
}

#[test]
fn end_of_options_and_inline_option_values_are_not_host_selectors() {
    for gui_launch in [false, true] {
        let cli = parse_argv(&["store", "--", "--gui"], gui_launch).unwrap();
        assert_eq!(cli.subcommand_opt.as_deref(), Some("--gui"));
        let cli = parse_argv(
            &[
                "store",
                "--transient-for=--gui",
                "--interaction=--help",
                "--desktop-id=--version",
                "--startup-notification-id=--gui",
            ],
            gui_launch,
        )
        .unwrap();
        assert_eq!(cli.transient_for.as_deref(), Some("--gui"));
        assert_eq!(cli.interaction.as_deref(), Some("--help"));
        assert_eq!(cli.desktop_id.as_deref(), Some("--version"));
        assert_eq!(cli.startup_notification_id.as_deref(), Some("--gui"));
    }
    let cli = parse_argv(&["store", "--gui", "--", "--gui"], true).unwrap();
    assert_eq!(cli.subcommand_opt.as_deref(), Some("--gui"));
}

#[test]
fn help_succeeds_but_version_remains_unconfigured() {
    for gui_launch in [false, true] {
        for flag in ["-h", "--help"] {
            let error = parse_argv(&["store", flag], gui_launch).unwrap_err();
            assert_eq!(error.kind(), ErrorKind::DisplayHelp);
            assert_eq!(error.exit_code(), 0);
            assert!(!error.use_stderr());
        }
        for flag in ["-V", "--version"] {
            let error = parse_argv(&["store", flag], gui_launch).unwrap_err();
            assert_eq!(error.kind(), ErrorKind::UnknownArgument);
            assert_eq!(error.exit_code(), 2);
        }
    }
    let help = parse_argv(&["renamed-store", "--gui", "--help"], true).unwrap_err();
    assert_eq!(help.exit_code(), 0);
    assert!(help.to_string().contains("Usage: renamed-store"));
    assert!(!help.to_string().contains("--gui"));
    assert_eq!(
        parse_argv(&["store", "--gui", "--version"], true)
            .unwrap_err()
            .exit_code(),
        2
    );
}

#[test]
fn invalid_flags_missing_values_and_extra_positionals_still_fail() {
    for gui_launch in [false, true] {
        for argv in [
            vec!["store", "--unknown"],
            vec!["store", "one", "two"],
            vec!["store", "--interaction", "one", "--interaction", "two"],
        ] {
            assert_eq!(parse_argv(&argv, gui_launch).unwrap_err().exit_code(), 2);
        }
        for option in [
            "--transient-for",
            "--interaction",
            "--desktop-id",
            "--startup-notification-id",
        ] {
            assert_eq!(
                parse_argv(&["store", option], gui_launch)
                    .unwrap_err()
                    .exit_code(),
                2
            );
            assert_eq!(
                parse_argv(&["store", option, "--gui"], gui_launch)
                    .unwrap_err()
                    .exit_code(),
                2
            );
        }
    }
}

#[cfg(unix)]
#[test]
fn os_arguments_retain_claps_existing_utf8_validation() {
    use std::os::unix::ffi::OsStringExt;

    let argv0 = OsString::from_vec(b"store-\xff".to_vec());
    let cli = parse_from([argv0.clone(), "--gui".into(), "search".into()], true).unwrap();
    assert_eq!(cli.subcommand_opt.as_deref(), Some("search"));
    for gui_launch in [false, true] {
        let error = parse_from(
            [argv0.clone(), OsString::from_vec(b"query-\xff".to_vec())],
            gui_launch,
        )
        .unwrap_err();
        assert_eq!(error.kind(), ErrorKind::InvalidUtf8);
        assert_eq!(error.exit_code(), 2);
    }
}
