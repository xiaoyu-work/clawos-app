use super::*;

fn parsed(args: &[&str], gui_launch: bool) -> Result<Outcome, String> {
    parse(args.iter().map(OsString::from), gui_launch)
}

fn run(args: &[&str], gui_launch: bool) -> Args {
    match parsed(args, gui_launch).unwrap() {
        Outcome::Run(args) => args,
        outcome => panic!("expected terminal startup, got {outcome:?}"),
    }
}

#[test]
fn gui_marker_preserves_the_native_command_and_option_order() {
    let direct = [
        "cosmic-term",
        "--no-daemon",
        "-w",
        "work dir",
        "-e",
        "printf",
        "%s",
        "first",
        "second",
    ];
    let mut gui = direct.to_vec();
    gui.insert(1, "--gui");
    assert_eq!(parsed(&gui, true), parsed(&direct, false));
    assert_eq!(
        run(&gui, true),
        Args {
            shell_program_opt: Some("printf".into()),
            shell_args: vec!["%s".into(), "first".into(), "second".into()],
            daemonize: false,
            working_directory: Some("work dir".into()),
        },
    );
}

#[test]
fn direct_and_duplicate_markers_remain_ignored_prefix_arguments() {
    for gui_launch in [false, true] {
        let args = run(
            &[
                "cosmic-term",
                "--gui",
                "--gui",
                "not-a-command",
                "--no-daemon",
            ],
            gui_launch,
        );
        assert!(!args.daemonize);
        assert_eq!(args.shell_program_opt, None);
        assert!(args.shell_args.is_empty());
        assert_eq!(
            run(
                &["cosmic-term", "ignored", "--gui", "-e", "real"],
                gui_launch
            )
            .shell_program_opt
            .as_deref(),
            Some("real"),
        );
    }
}

#[test]
fn argv_zero_keeps_its_existing_parser_role() {
    for gui_launch in [false, true] {
        assert_eq!(parsed(&["--help"], gui_launch), Ok(Outcome::Help));
        assert_eq!(parsed(&["--version"], gui_launch), Ok(Outcome::Version));
        assert_eq!(
            run(&["-w", "directory"], gui_launch).working_directory,
            Some("directory".into()),
        );
        assert_eq!(run(&["cosmic-term"], gui_launch).shell_program_opt, None);
    }
}

#[test]
fn help_and_version_keep_their_early_exit_behavior() {
    for (flag, outcome) in [
        ("--help", Outcome::Help),
        ("-h", Outcome::Help),
        ("--version", Outcome::Version),
        ("-V", Outcome::Version),
    ] {
        assert_eq!(parsed(&["cosmic-term", flag, "-w"], false), Ok(outcome),);
        assert_eq!(
            parsed(&["cosmic-term", "--gui", flag, "-w"], true),
            parsed(&["cosmic-term", flag, "-w"], false),
        );
    }
}

#[test]
fn working_directory_consumes_markers_and_option_like_values() {
    for flag in ["-w", "--working-directory"] {
        for value in ["--gui", "--", "--help", "--no-daemon", "-e"] {
            for gui_launch in [false, true] {
                let args = run(&["cosmic-term", flag, value], gui_launch);
                assert_eq!(args.working_directory, Some(PathBuf::from(value)));
                assert!(args.daemonize);
                assert_eq!(args.shell_program_opt, None);
            }
            assert_eq!(
                run(&["cosmic-term", "--gui", flag, value], true).working_directory,
                Some(PathBuf::from(value)),
            );
        }
    }
}

#[test]
fn the_last_working_directory_value_still_wins() {
    assert_eq!(
        run(
            &[
                "cosmic-term",
                "--gui",
                "-w",
                "first",
                "--working-directory",
                "last"
            ],
            true,
        )
        .working_directory,
        Some("last".into()),
    );
}

#[test]
fn missing_working_directory_preserves_the_native_error() {
    for flag in ["-w", "--working-directory"] {
        assert_eq!(
            parsed(&["cosmic-term", flag], false),
            Err(format!("Missing argument for {flag}")),
        );
        assert_eq!(
            parsed(&["cosmic-term", "--gui", flag], true),
            Err(format!("Missing argument for {flag}")),
        );
    }
}

#[test]
fn every_command_delimiter_preserves_all_suffix_arguments() {
    for delimiter in ["-e", "--command", "--"] {
        for gui_launch in [false, true] {
            let mut argv = vec!["cosmic-term"];
            if gui_launch {
                argv.push("--gui");
            }
            argv.extend([
                delimiter,
                "--gui",
                "--help",
                "--version",
                "--no-daemon",
                "-w",
                "--",
                "",
                "last",
            ]);
            assert_eq!(
                run(&argv, gui_launch),
                Args {
                    shell_program_opt: Some("--gui".into()),
                    shell_args: ["--help", "--version", "--no-daemon", "-w", "--", "", "last"]
                        .map(String::from)
                        .to_vec(),
                    daemonize: true,
                    working_directory: None,
                },
            );
        }
    }
}

#[test]
fn a_command_delimiter_without_a_program_still_uses_the_default_shell() {
    for delimiter in ["-e", "--command", "--"] {
        assert_eq!(
            run(&["cosmic-term", "--gui", delimiter], true),
            run(&["cosmic-term", delimiter], false),
        );
        assert_eq!(
            run(&["cosmic-term", delimiter], false).shell_program_opt,
            None,
        );
    }
}

#[cfg(unix)]
#[test]
fn working_directory_bytes_are_preserved_and_unknown_bytes_are_ignored() {
    use std::os::unix::ffi::OsStringExt;

    let directory = OsString::from_vec(b"work-\xff".to_vec());
    let outcome = parse(
        [
            OsString::from_vec(b"terminal-\xfe".to_vec()),
            OsString::from("--gui"),
            OsString::from_vec(b"unknown-\xfd".to_vec()),
            OsString::from("-w"),
            directory.clone(),
            OsString::from("--no-daemon"),
        ],
        true,
    );
    assert_eq!(
        outcome,
        Ok(Outcome::Run(Args {
            shell_program_opt: None,
            shell_args: Vec::new(),
            daemonize: false,
            working_directory: Some(PathBuf::from(directory)),
        })),
    );
}
