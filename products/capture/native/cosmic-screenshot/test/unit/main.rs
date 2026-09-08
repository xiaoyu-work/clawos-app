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
