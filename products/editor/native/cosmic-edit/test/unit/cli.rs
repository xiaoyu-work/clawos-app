use super::*;

fn paths(args: &[&str], gui_launch: bool) -> Vec<PathBuf> {
    parse(args.iter().map(OsString::from), gui_launch)
}

#[test]
fn gui_launch_removes_only_the_leading_host_marker() {
    assert_eq!(
        paths(
            &["cosmic-edit", "--gui", "first file", "--gui", "last"],
            true
        ),
        vec![
            PathBuf::from("first file"),
            PathBuf::from("--gui"),
            PathBuf::from("last"),
        ],
    );
}

#[test]
fn direct_launch_treats_every_argument_as_a_filename() {
    let args = [
        "cosmic-edit",
        "--gui",
        "--help",
        "--version",
        "-w",
        "directory",
        "--",
        "file",
    ];
    assert_eq!(
        paths(&args, false),
        args[1..].iter().map(PathBuf::from).collect::<Vec<_>>(),
    );
    let mut gui_args = args.to_vec();
    gui_args.insert(1, "--gui");
    assert_eq!(paths(&gui_args, true), paths(&args, false));
}

#[test]
fn marker_after_a_path_or_delimiter_is_still_a_filename() {
    for args in [
        ["cosmic-edit", "file", "--gui"],
        ["cosmic-edit", "--", "--gui"],
    ] {
        assert_eq!(paths(&args, true), paths(&args, false));
        assert_eq!(
            paths(&args, true),
            args[1..].iter().map(PathBuf::from).collect::<Vec<_>>(),
        );
    }
}

#[test]
fn argv_zero_is_never_a_path_or_a_host_marker() {
    assert_eq!(paths(&["--gui", "file"], true), vec![PathBuf::from("file")],);
    for gui_launch in [false, true] {
        assert!(paths(&[], gui_launch).is_empty());
        assert!(paths(&["--gui"], gui_launch).is_empty());
    }
    assert!(paths(&["cosmic-edit", "--gui"], true).is_empty());
}

#[cfg(unix)]
#[test]
fn filenames_and_argv_zero_preserve_non_utf8_bytes() {
    use std::os::unix::ffi::OsStringExt;

    let program = OsString::from_vec(b"editor-\xff".to_vec());
    let file = OsString::from_vec(b"file-\xfe".to_vec());
    for gui_launch in [false, true] {
        let mut argv = vec![program.clone()];
        if gui_launch {
            argv.push(OsString::from("--gui"));
        }
        argv.extend([file.clone(), OsString::from("last")]);
        assert_eq!(
            parse(argv, gui_launch),
            vec![PathBuf::from(&file), PathBuf::from("last")],
        );
    }
}
