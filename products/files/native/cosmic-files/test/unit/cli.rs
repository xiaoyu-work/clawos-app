use super::*;

fn parsed(args: &[&str], gui_launch: bool, show_recents: bool) -> (Args, Vec<PathBuf>) {
    let mut paths = Vec::new();
    let parsed = parse(
        args.iter().map(OsString::from),
        gui_launch,
        show_recents,
        |path| {
            paths.push(path.to_path_buf());
            Ok(Path::new("/canonical").join(path))
        },
    );
    (parsed, paths)
}

#[test]
fn direct_marker_is_a_path_and_gui_removes_only_one_leading_marker() {
    let args = ["cosmic-files", "--gui", "--gui", "last"];
    let (direct, direct_paths) = parsed(&args, false, true);
    assert_eq!(direct_paths, ["--gui", "--gui", "last"].map(PathBuf::from),);
    assert_eq!(
        direct.locations,
        direct_paths
            .iter()
            .map(|path| Location::Path(Path::new("/canonical").join(path)))
            .collect::<Vec<_>>(),
    );

    let (gui, gui_paths) = parsed(&args, true, true);
    assert_eq!(gui_paths, ["--gui", "last"].map(PathBuf::from));
    assert_eq!(gui.locations, direct.locations[1..]);
    assert!(gui.daemonize);
    assert!(gui.uris.is_empty());
}

#[test]
fn argv_zero_is_skipped_without_becoming_a_selector_or_uri() {
    for program in ["--gui", "--trash", "smb://server/share"] {
        for gui_launch in [false, true] {
            let (args, paths) = parsed(&[program, "file"], gui_launch, true);
            assert_eq!(paths, [PathBuf::from("file")]);
            assert_eq!(args.locations, [Location::Path("/canonical/file".into())]);
            assert!(args.uris.is_empty());
        }
    }
    assert!(parsed(&[], true, true).0.locations.is_empty());
    assert!(
        parsed(&["cosmic-files", "--gui"], true, true)
            .0
            .locations
            .is_empty()
    );
}

#[test]
fn flags_file_urls_and_other_uris_keep_their_existing_ordering() {
    let args = [
        "cosmic-files",
        "--no-daemon",
        "first",
        "smb://server/first",
        "--trash",
        "file:///documents/second%20file",
        "--recents",
        "https://example.invalid/last",
        "--network",
        "last",
    ];
    let (direct, paths) = parsed(&args, false, true);
    let mut gui = args.to_vec();
    gui.insert(1, "--gui");
    assert_eq!(parsed(&gui, true, true), (direct, paths.clone()));
    let (args, _) = parsed(&args, false, true);
    assert!(!args.daemonize);
    assert_eq!(
        paths,
        ["first", "/documents/second file", "last"].map(PathBuf::from),
    );
    assert_eq!(
        args.locations,
        [
            Location::Path("/canonical/first".into()),
            Location::Trash,
            Location::Path("/documents/second file".into()),
            Location::Recents,
            Location::Network("network:///".into(), crate::fl!("networks"), None),
            Location::Path("/canonical/last".into()),
        ],
    );
    assert_eq!(
        args.uris,
        [
            url::Url::parse("smb://server/first").unwrap(),
            url::Url::parse("https://example.invalid/last").unwrap(),
        ],
    );
}

#[test]
fn recents_still_depends_on_config() {
    let argv = ["cosmic-files", "--gui", "--recents", "--trash", "--recents"];
    let (disabled, paths) = parsed(&argv, true, false);
    assert_eq!(disabled.locations, [Location::Trash]);
    assert!(paths.is_empty());
    assert_eq!(
        parsed(&argv, true, true).0.locations,
        [Location::Recents, Location::Trash, Location::Recents],
    );
}

#[test]
fn double_dash_does_not_end_option_scanning() {
    let argv = [
        "cosmic-files",
        "--gui",
        "--",
        "--trash",
        "--no-daemon",
        "--gui",
        "--help",
    ];
    let (args, paths) = parsed(&argv, true, true);
    assert!(!args.daemonize);
    assert_eq!(paths, ["--", "--gui", "--help"].map(PathBuf::from));
    assert_eq!(
        args.locations,
        [
            Location::Path("/canonical/--".into()),
            Location::Trash,
            Location::Path("/canonical/--gui".into()),
            Location::Path("/canonical/--help".into()),
        ],
    );
}

#[test]
fn a_later_marker_is_not_removed_in_gui_mode() {
    let argv = ["cosmic-files", "file", "--gui", "--trash"];
    assert_eq!(parsed(&argv, true, true), parsed(&argv, false, true));
    assert_eq!(
        parsed(&argv, true, true).1,
        ["file", "--gui"].map(PathBuf::from),
    );
}

#[test]
fn invalid_file_urls_and_canonicalization_errors_are_still_skipped() {
    let mut paths = Vec::new();
    let args = parse(
        [
            "cosmic-files",
            "--gui",
            "file://remote.invalid/not-local",
            "missing",
            "--trash",
            "valid",
        ]
        .map(OsString::from),
        true,
        true,
        |path| {
            paths.push(path.to_path_buf());
            if path == Path::new("missing") {
                Err(io::Error::new(io::ErrorKind::NotFound, "missing fixture"))
            } else {
                Ok(Path::new("/canonical").join(path))
            }
        },
    );
    assert_eq!(paths, ["missing", "valid"].map(PathBuf::from));
    assert_eq!(
        args.locations,
        [Location::Trash, Location::Path("/canonical/valid".into())],
    );
    assert!(args.uris.is_empty());
}

#[test]
fn real_file_urls_are_canonicalized_like_native_paths() {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("Cargo.toml");
    let url = url::Url::from_file_path(&path).unwrap();
    let args = parse(
        [
            OsString::from("cosmic-files"),
            OsString::from("--gui"),
            path.clone().into_os_string(),
            OsString::from(url.as_str()),
        ],
        true,
        true,
        |path| std::fs::canonicalize(path),
    );
    let absolute = std::fs::canonicalize(path).unwrap();
    assert_eq!(
        args.locations,
        [Location::Path(absolute.clone()), Location::Path(absolute)],
    );
    assert!(args.uris.is_empty());
}

#[cfg(unix)]
#[test]
fn native_paths_and_file_urls_preserve_non_utf8_bytes() {
    use std::os::unix::ffi::OsStringExt;

    let file = PathBuf::from(OsString::from_vec(b"/documents/file-\xff".to_vec()));
    let file_url = url::Url::from_file_path(&file).unwrap();
    let args = parse(
        [
            OsString::from_vec(b"files-\xfe".to_vec()),
            OsString::from("--gui"),
            file.clone().into_os_string(),
            OsString::from(file_url.as_str()),
        ],
        true,
        true,
        |path| Ok(path.to_path_buf()),
    );
    assert_eq!(
        args.locations,
        [Location::Path(file.clone()), Location::Path(file)],
    );
    assert!(args.uris.is_empty());
}
