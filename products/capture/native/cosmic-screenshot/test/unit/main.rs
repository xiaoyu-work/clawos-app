use super::*;

#[test]
fn native_cli_preserves_original_interactive_modal_and_notification_defaults() {
    let args = Args::try_parse_from(["cosmic-screenshot"]).unwrap();
    assert!(args.interactive && args.modal && args.notify);
    assert!(!args.portal_capture_stdout);
    assert_eq!(args.save_dir, None);
    let args = Args::try_parse_from([
        "cosmic-screenshot",
        "--interactive=false",
        "--modal=false",
        "--notify=false",
        "--save-dir",
        "shots",
    ])
    .unwrap();
    assert!(!args.interactive && !args.modal && !args.notify);
    assert_eq!(args.save_dir, Some(PathBuf::from("shots")));
    assert!(
        Args::try_parse_from([
            "cosmic-screenshot",
            "--portal-capture-stdout",
            "--save-dir",
            "/work"
        ])
        .is_err()
    );
}

fn launch_args(argv: &[&str], gui: bool) -> Result<Args, clap::Error> {
    Args::try_parse_from(claw_app_gui_argv::normalize(
        argv.iter().map(std::ffi::OsString::from),
        gui,
        std::ffi::OsStr::new("--gui"),
    ))
}

#[test]
fn native_gui_argv_preserves_capture_options_and_values() {
    for arguments in [
        vec![],
        vec!["--interactive=false", "--modal=false", "--notify=false"],
        vec!["--save-dir", "shots with spaces"],
        vec!["--save-dir=--gui", "--notify=false"],
        vec!["--portal-capture-stdout", "--modal=false"],
    ] {
        let mut direct = vec!["cosmic-screenshot"];
        direct.extend_from_slice(&arguments);
        let mut gui = vec!["cosmic-screenshot", "--gui"];
        gui.extend_from_slice(&arguments);
        assert_eq!(
            launch_args(&direct, false).unwrap(),
            launch_args(&gui, true).unwrap(),
        );
    }
}

#[test]
fn native_gui_argv_retains_clap_help_version_and_valid_errors() {
    for arguments in [
        vec!["--help"],
        vec!["--version"],
        vec!["--unknown"],
        vec!["--save-dir"],
        vec!["--save-dir", "--gui"],
        vec!["--", "--gui"],
        vec!["--interactive", "false"],
        vec!["--portal-capture-stdout", "--save-dir", "shots"],
    ] {
        let mut direct = vec!["cosmic-screenshot"];
        direct.extend_from_slice(&arguments);
        let mut gui = vec!["cosmic-screenshot", "--gui"];
        gui.extend_from_slice(&arguments);
        let direct = launch_args(&direct, false).unwrap_err();
        let gui = launch_args(&gui, true).unwrap_err();
        assert_eq!(direct.kind(), gui.kind());
        assert_eq!(direct.exit_code(), gui.exit_code());
        assert_eq!(direct.to_string(), gui.to_string());
    }
}

#[test]
fn native_gui_argv_retains_direct_and_repeated_flags() {
    let direct = launch_args(&["cosmic-screenshot", "--gui"], false).unwrap_err();
    let repeated = launch_args(&["cosmic-screenshot", "--gui", "--gui"], true).unwrap_err();
    assert_eq!(direct.kind(), clap::error::ErrorKind::UnknownArgument);
    assert_eq!(direct.to_string(), repeated.to_string());
    assert_eq!(
        launch_args(&["cosmic-screenshot"], false).unwrap(),
        launch_args(&["cosmic-screenshot"], true).unwrap(),
    );
}

#[test]
fn native_gui_argv_preserves_non_utf8_save_paths() {
    use std::ffi::OsString;
    use std::os::unix::ffi::OsStringExt;

    let path = OsString::from_vec(b"shots-\xff".to_vec());
    let args = Args::try_parse_from(claw_app_gui_argv::normalize(
        [
            OsString::from("cosmic-screenshot"),
            OsString::from("--gui"),
            OsString::from("--save-dir"),
            path.clone(),
        ],
        true,
        std::ffi::OsStr::new("--gui"),
    ))
    .unwrap();
    assert_eq!(args.save_dir, Some(PathBuf::from(path)));
}

#[test]
fn portal_png_is_bounded_regular_private_input_not_arbitrary_file_or_symlink() {
    let dir = tempfile::tempdir_in(std::env::current_dir().unwrap()).unwrap();
    let image = dir.path().join("image.png");
    fs::write(&image, b"\x89PNG\r\n\x1a\nfixture").unwrap();
    assert_eq!(
        read_portal_png(image.to_str().unwrap()).unwrap(),
        b"\x89PNG\r\n\x1a\nfixture"
    );
    assert!(!image.exists());
    fs::write(&image, "not PNG").unwrap();
    assert!(read_portal_png(image.to_str().unwrap()).is_err());
    assert!(image.exists());
    let link = dir.path().join("link");
    std::os::unix::fs::symlink(&image, &link).unwrap();
    assert!(read_portal_png(link.to_str().unwrap()).is_err());
    assert!(image.exists());
    assert!(read_portal_png(dir.path().to_str().unwrap()).is_err());
    fs::OpenOptions::new()
        .write(true)
        .open(&image)
        .unwrap()
        .set_len(64 * 1024 * 1024 + 1)
        .unwrap();
    assert!(read_portal_png(image.to_str().unwrap()).is_err());
}

#[test]
fn all_original_notification_strings_remain_embedded() {
    crate::localize::localize();
    assert!(!fl!("cosmic-screenshot").is_empty());
    assert!(!fl!("screenshot-saved-to").is_empty());
    assert!(!fl!("screenshot-saved-to-clipboard").is_empty());
}
