use super::*;

#[test]
fn retained_shared_config_ids_construct_without_turning_missing_grants_into_writes() {
    const CHILD: &str = "CLAW_SETTINGS_DENIED_CONFIG_TEST";
    if std::env::var_os(CHILD).is_none() {
        let output=std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--exact","owner_config::tests::retained_shared_config_ids_construct_without_turning_missing_grants_into_writes","--test-threads=1","--nocapture"])
            .env_clear().env(CHILD,"1").output().unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        return;
    }
    for (id, key) in [
        (cosmic_settings_config::shortcuts::ID, "custom"),
        (
            cosmic_settings_config::window_rules::ID,
            "tiling_exception_custom",
        ),
        (cosmic_bg_config::NAME, "backgrounds"),
        (cosmic_settings_daemon_config::NAME, "mono_sound"),
    ] {
        let config = Config::new(id, 1)
            .expect("retained public type ID must select the existing closed OS resource");
        assert!(config.get::<Vec<String>>(key).is_err());
        assert!(config.set(key, Vec::<String>::new()).is_err());
        assert!(!config.ready);
        assert!(config.path.is_none());
    }
    assert!(Config::new("unregistered.owner.config", 1).is_err());
}

#[test]
fn owner_preferences_require_correlated_confirmations_and_never_treat_review_as_saved() {
    let entries = vec![Entry {
        key: "xkb_config".into(),
        value: "(layout:\"de\")".into(),
    }];
    let response = json!({
        "action":"write","namespace":"compositor","version":1,"status":"applied","entries":entries,
    });
    assert_eq!(
        decode("compositor", "write", &entries, response.clone()).unwrap(),
        entries
    );
    for (key, value) in [
        ("namespace", json!("other")),
        ("action", json!("read")),
        ("version", json!(2)),
        ("status", json!("pending")),
        (
            "entries",
            json!([{"key":"xkb_config","value":"(layout:\"us\")"}]),
        ),
    ] {
        let mut wrong = response.clone();
        wrong[key] = value;
        assert!(
            decode("compositor", "write", &entries, wrong).is_err(),
            "{key}"
        );
    }
    assert!(
        decode(
            "compositor",
            "write",
            &entries,
            json!({
                "status":"system_review_required","system_review_id":"not-authority",
            })
        )
        .is_err()
    );
    assert!(
        decode(
            "compositor",
            "read",
            &[],
            json!({
                "action":"read","namespace":"compositor","version":1,
                "entries":[{"key":"../other","value":"1"}],
            })
        )
        .is_err()
    );
}
