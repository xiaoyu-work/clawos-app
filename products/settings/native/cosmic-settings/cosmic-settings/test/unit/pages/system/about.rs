use super::*;

fn page() -> Page {
    let mut page = Page::default();
    page.info.device_name = "old-host".into();
    page.hostname_input = "new-host".into();
    page
}

#[test]
fn hostname_failure_keeps_attempted_input_and_never_changes_observed_name() {
    for failure in [
        Failure::Denied("missing grant".into()),
        Failure::Review("rv-pending".into()),
        Failure::Unavailable("offline".into()),
        Failure::Unconfirmed("lost acknowledgement".into()),
    ] {
        let mut page = page();
        let generation = page.pending.begin().unwrap();
        let _task = page.update(Message::HostnameFinished(
            generation,
            "new-host".into(),
            Err(failure),
        ));
        assert_eq!(page.info.device_name, "old-host");
        assert_eq!(page.hostname_input, "new-host");
        assert!(page.editing_device_name);
        assert!(!page.pending.busy());
        assert!(page.notice.is_some());
    }
}

#[test]
fn matching_hostname_confirmation_is_not_overwritten_by_stale_info_or_duplicate_completion() {
    let mut page = page();
    let old_revision = page.pending.revision();
    let generation = page.pending.begin().unwrap();
    let _task = page.update(Message::HostnameFinished(
        generation,
        "new-host".into(),
        Ok(()),
    ));
    assert_eq!(page.info.device_name, "new-host");
    let _task = page.update(Message::HostnameFinished(
        generation,
        "forged-old-host".into(),
        Ok(()),
    ));
    let mut old = Info::default();
    old.device_name = "old-host".into();
    let _task = page.update(Message::Info(old_revision, Box::new(old)));
    assert_eq!(page.info.device_name, "new-host");
}

#[test]
fn pending_hostname_disables_duplicate_submit_and_invalid_input_is_visible() {
    let mut page = page();
    let generation = page.pending.begin().unwrap();
    let _task = page.update(Message::HostnameSubmit);
    assert_eq!(page.pending.revision(), (generation, true));
    assert_eq!(page.info.device_name, "old-host");
    page.pending.complete(generation);
    page.hostname_input = "bad hostname".into();
    let _task = page.update(Message::HostnameSubmit);
    assert!(!page.pending.busy());
    assert!(page.notice.is_some());
    assert_eq!(page.hostname_input, "bad hostname");
}

#[test]
fn hostname_source_has_no_direct_privileged_dbus_or_helper_fallback() {
    let source = include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/src/pages/system/about.rs"
    ));
    assert!(!source.contains("set_static_hostname"));
    assert!(!source.contains("zbus::"));
    assert!(!source.contains("pkexec"));
    assert!(!source.contains("approval-helper"));
}
