use super::*;
use std::cell::RefCell;
use std::sync::Once;

thread_local! {
    static WARNINGS: RefCell<Vec<String>> = const { RefCell::new(Vec::new()) };
}

struct WarningLog;

impl log::Log for WarningLog {
    fn enabled(&self, metadata: &log::Metadata<'_>) -> bool {
        metadata.level() <= log::Level::Warn
    }

    fn log(&self, record: &log::Record<'_>) {
        if self.enabled(record.metadata()) {
            WARNINGS.with(|warnings| warnings.borrow_mut().push(record.args().to_string()));
        }
    }

    fn flush(&self) {}
}

fn parse_argv(argv: &[&str], gui_launch: bool) -> Result<Arguments, DisplayRequest> {
    parse_from(argv.iter().map(OsString::from), gui_launch)
}

fn parse_with_warnings(argv: &[&str], gui_launch: bool) -> (Arguments, Vec<String>) {
    static INIT: Once = Once::new();
    INIT.call_once(|| {
        log::set_logger(&WarningLog).unwrap();
        log::set_max_level(log::LevelFilter::Warn);
    });
    WARNINGS.with(|warnings| warnings.borrow_mut().clear());
    let args = parse_argv(argv, gui_launch).unwrap();
    let warnings = WARNINGS.with(|warnings| std::mem::take(&mut *warnings.borrow_mut()));
    (args, warnings)
}

#[test]
fn gui_mode_suppresses_only_one_leading_selector_warning() {
    for gui_launch in [false, true] {
        for (argv, count) in [
            (vec!["player", "--gui"], if gui_launch { 0 } else { 1 }),
            (
                vec!["player", "--gui", "--gui"],
                if gui_launch { 1 } else { 2 },
            ),
            (vec!["player", "https://example.test/one", "--gui"], 1),
        ] {
            let (_, warnings) = parse_with_warnings(&argv, gui_launch);
            assert_eq!(warnings, vec!["unexpected flag: --gui"; count]);
        }
        let (args, warnings) = parse_with_warnings(&["player", "--thumbnail", "--gui"], gui_launch);
        assert_eq!(args.thumbnail_opt, Some(PathBuf::from("--gui")));
        assert!(warnings.is_empty());
    }
}

#[test]
fn argv0_is_skipped_and_gui_mode_does_not_change_ordinary_inputs() {
    for gui_launch in [false, true] {
        for argv0 in ["player", "--gui", "https://example.test/not-media"] {
            let args = parse_argv(&[argv0], gui_launch).unwrap();
            assert!(args.url_opt.is_none());
            assert!(args.urls.is_none());
        }
        for argv in [
            vec!["player", "https://example.test/one"],
            vec!["player", "--gui", "https://example.test/one"],
        ] {
            let args = parse_argv(&argv, gui_launch).unwrap();
            assert_eq!(args.url_opt.unwrap().as_str(), "https://example.test/one");
            assert!(args.urls.is_none());
        }
    }
}

#[test]
fn files_uris_flags_and_duplicate_urls_keep_encounter_order() {
    let local = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("src/../Cargo.toml");
    let local_url = Url::from_file_path(fs::canonicalize(&local).unwrap()).unwrap();
    let first = "https://example.test/media?q=--gui";
    let last = "file:///fixture/media%20clip.mp4";
    for gui_launch in [false, true] {
        let mut argv = vec![OsString::from("player")];
        if gui_launch {
            argv.push("--gui".into());
        }
        argv.extend([
            first.into(),
            "--size=64x32".into(),
            local.clone().into_os_string(),
            "--unknown".into(),
            last.into(),
            "--thumbnail=output.png".into(),
            first.into(),
        ]);
        let args = parse_from(argv, gui_launch).unwrap();
        assert!(args.url_opt.is_none());
        assert_eq!(
            args.urls.unwrap(),
            [
                Url::parse(first).unwrap(),
                local_url.clone(),
                Url::parse(last).unwrap(),
                Url::parse(first).unwrap(),
            ]
        );
        assert_eq!(args.size_opt, Some((64, 32)));
        assert_eq!(args.thumbnail_opt, Some(PathBuf::from("output.png")));
    }
}

#[test]
fn consumed_option_values_and_later_selectors_are_preserved() {
    for gui_launch in [false, true] {
        for argv in [
            vec!["player", "--thumbnail", "--gui"],
            vec!["player", "--thumbnail=--gui"],
            vec!["player", "--gui", "--gui", "--thumbnail", "--gui"],
        ] {
            let args = parse_argv(&argv, gui_launch).unwrap();
            assert_eq!(args.thumbnail_opt, Some(PathBuf::from("--gui")));
        }
        for value in ["--help", "--version", "--gui"] {
            let args = parse_argv(&["player", "--thumbnail", value], gui_launch).unwrap();
            assert_eq!(args.thumbnail_opt, Some(PathBuf::from(value)));
            let args = parse_argv(
                &["player", "--size", value, "https://example.test/one"],
                gui_launch,
            )
            .unwrap();
            assert!(args.size_opt.is_none());
            assert_eq!(args.url_opt.unwrap().as_str(), "https://example.test/one");
        }
    }
}

#[test]
fn double_dash_does_not_introduce_a_new_end_of_options_state() {
    for gui_launch in [false, true] {
        let args = parse_argv(
            &[
                "player",
                "--",
                "--gui",
                "--size",
                "23",
                "--thumbnail",
                "out.png",
                "https://example.test/one",
            ],
            gui_launch,
        )
        .unwrap();
        assert_eq!(args.size_opt, Some((23, 23)));
        assert_eq!(args.thumbnail_opt, Some(PathBuf::from("out.png")));
        assert_eq!(args.url_opt.unwrap().as_str(), "https://example.test/one");
    }
}

#[test]
fn size_forms_and_last_valid_value_behavior_are_unchanged() {
    for gui_launch in [false, true] {
        for (value, expected) in [
            ("80", (80, 80)),
            ("80x45", (80, 45)),
            ("0", (0, 0)),
            ("9x8x7", (9, 8)),
        ] {
            let inline = format!("--size={value}");
            for argv in [vec!["player", "--size", value], vec!["player", &inline]] {
                assert_eq!(
                    parse_argv(&argv, gui_launch).unwrap().size_opt,
                    Some(expected)
                );
            }
        }
        let args = parse_argv(
            &[
                "player",
                "--size=7x8",
                "--size=bad",
                "--size=3xbad",
                "--size",
                "5",
                "--thumbnail=first",
                "--thumbnail",
                "last",
                "--size",
            ],
            gui_launch,
        )
        .unwrap();
        assert_eq!(args.size_opt, Some((5, 5)));
        assert_eq!(args.thumbnail_opt, Some(PathBuf::from("last")));
    }
}

#[test]
fn unknown_flags_bad_sizes_and_missing_values_keep_parsing() {
    for gui_launch in [false, true] {
        let (args, warnings) = parse_with_warnings(
            &[
                "player",
                "--unknown",
                "-q",
                "--gui=value",
                "--size=bad",
                "--size=3xbad",
                "https://example.test/one",
                "--thumbnail",
            ],
            gui_launch,
        );
        assert!(args.size_opt.is_none());
        assert!(args.thumbnail_opt.is_none());
        assert_eq!(args.url_opt.unwrap().as_str(), "https://example.test/one");
        assert_eq!(warnings.len(), 6);
        assert_eq!(
            &warnings[..3],
            [
                "unexpected flag: --unknown",
                "unexpected flag: -q",
                "unexpected flag: --gui=value",
            ]
        );
        assert!(warnings[3].starts_with("failed to parse size 'bad':"));
        assert!(warnings[4].starts_with("failed to parse size '3xbad':"));
        assert_eq!(warnings[5], "thumbnail requires value");
    }
}

#[test]
fn help_and_version_still_request_immediate_successful_display() {
    for (flag, expected) in [
        ("-h", DisplayRequest::Help),
        ("--help", DisplayRequest::Help),
        ("--help=ignored", DisplayRequest::Help),
        ("-hV", DisplayRequest::Help),
        ("-V", DisplayRequest::Version),
        ("--version", DisplayRequest::Version),
        ("--version=ignored", DisplayRequest::Version),
        ("-Vh", DisplayRequest::Version),
    ] {
        for gui_launch in [false, true] {
            assert_eq!(
                parse_argv(&["player", flag], gui_launch).unwrap_err(),
                expected
            );
        }
        assert_eq!(
            parse_argv(&["player", "--gui", flag], true).unwrap_err(),
            expected
        );
        assert_eq!(
            parse_argv(&["player", flag, "--unknown"], true).unwrap_err(),
            expected
        );
    }
}

#[cfg(unix)]
#[test]
fn non_utf8_thumbnail_values_survive_and_non_utf8_positionals_are_skipped() {
    use std::os::unix::ffi::OsStringExt;

    let output = OsString::from_vec(b"--gui-\xff.png".to_vec());
    let inline = OsString::from_vec(b"--thumbnail=--gui-\xff.png".to_vec());
    for gui_launch in [false, true] {
        for option in [
            vec!["--thumbnail".into(), output.clone()],
            vec![inline.clone()],
        ] {
            let mut argv = vec![OsString::from_vec(b"player-\xff".to_vec())];
            if gui_launch {
                argv.push("--gui".into());
            }
            argv.extend(option);
            argv.push(OsString::from_vec(b"positional-\xff".to_vec()));
            argv.push("https://example.test/one".into());
            let args = parse_from(argv, gui_launch).unwrap();
            assert_eq!(args.thumbnail_opt, Some(PathBuf::from(&output)));
            assert_eq!(args.url_opt.unwrap().as_str(), "https://example.test/one");
            assert!(args.urls.is_none());
        }
    }
}
