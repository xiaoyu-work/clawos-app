use super::*;
use serde_json::json;

#[test]
fn confirmation_requires_the_matching_action_value_and_closed_response() {
    let change = Change::StaticHostname {
        hostname: "new-host".into(),
    };
    decode(
        &change,
        json!({"action":"static_hostname","status":"applied","hostname":"new-host"}),
    )
    .unwrap();
    for response in [
        json!({"action":"static_hostname","status":"pending","hostname":"new-host"}),
        json!({"action":"static_hostname","status":"applied","hostname":"another-host"}),
        json!({"action":"owner_language","status":"applied","language":"new-host"}),
        json!({"action":"static_hostname","status":"applied","hostname":"new-host","approved":true}),
        json!({"ok":true}),
        json!({"status":"applied"}),
        Value::Null,
    ] {
        assert!(matches!(
            decode(&change, response),
            Err(Failure::Unconfirmed(_))
        ));
    }
}

#[test]
fn review_is_pending_not_a_write_confirmation_or_an_app_approval() {
    let change = Change::OwnerLanguage {
        languages: "de_DE:de:en".into(),
    };
    assert_eq!(
        decode(
            &change,
            json!({"status":"system_review_required","system_review_id":"rv-test"})
        ),
        Err(Failure::Review("rv-test".into()))
    );
    assert!(
        decode(
            &change,
            json!({"status":"system_review_required","system_review_id":"../root"})
        )
        .is_err()
    );
    decode(
        &change,
        json!({"action":"owner_language","status":"applied","language":"de_DE:de:en"}),
    )
    .unwrap();
    assert!(
        decode(
            &change,
            json!({"action":"owner_language","status":"applied","language":"en"})
        )
        .is_err()
    );
}

#[test]
fn locale_confirmation_requires_all_ten_exact_effective_values() {
    let change = Change::SystemLocale {
        lang: "en_US.UTF-8".into(),
        region: "de_DE.UTF-8".into(),
    };
    let mut values = vec!["LANG=en_US.UTF-8".to_owned()];
    for name in [
        "LC_ADDRESS",
        "LC_IDENTIFICATION",
        "LC_MEASUREMENT",
        "LC_MONETARY",
        "LC_NAME",
        "LC_NUMERIC",
        "LC_PAPER",
        "LC_TELEPHONE",
        "LC_TIME",
    ] {
        values.push(format!("{name}=de_DE.UTF-8"));
    }
    decode(
        &change,
        json!({"action":"system_locale","status":"applied","locale":values}),
    )
    .unwrap();
    values[1] = "LANG=fr_FR.UTF-8".into();
    assert!(
        decode(
            &change,
            json!({"action":"system_locale","status":"applied","locale":values})
        )
        .is_err()
    );
}

#[test]
fn denied_and_ambiguous_transport_errors_never_confirm_a_change() {
    assert_eq!(
        classify(claw_os_sdk::BridgeError::AppError {
            app: "regional-settings".into(),
            verb: "control".into(),
            message: "missing grant".into(),
            code: "PERMISSION_DENIED".into(),
        }),
        Failure::Denied("missing grant".into())
    );
    assert!(matches!(
        classify(claw_os_sdk::BridgeError::AppError {
            app: "regional-settings".into(),
            verb: "control".into(),
            message: "lost acknowledgement".into(),
            code: "INDETERMINATE".into(),
        }),
        Failure::Unconfirmed(_)
    ));
    assert!(matches!(
        classify(claw_os_sdk::BridgeError::Decode {
            app: "regional-settings".into(),
            verb: "control".into(),
            message: "malformed".into(),
        }),
        Failure::Unconfirmed(_)
    ));
}

#[test]
fn duplicate_actions_and_stale_completions_or_queries_cannot_overwrite_state() {
    let mut pending = Pending::default();
    let before = pending.revision();
    let first = pending.begin().unwrap();
    let during = pending.revision();
    assert!(pending.begin().is_err());
    assert!(!pending.complete(first + 1));
    assert!(pending.busy());
    assert!(pending.complete(first));
    assert_ne!(pending.revision(), before);
    assert_ne!(pending.revision(), during);
    assert!(!pending.complete(first));
    let second = pending.begin().unwrap();
    assert!(!pending.complete(first));
    assert!(pending.complete(second));
}

#[test]
fn client_uses_only_the_fixed_public_sdk_service_bridge() {
    let source = include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/src/regional_settings.rs"
    ));
    assert!(source.contains("cos_call_json_async_with_binary"));
    assert!(source.contains("\"/usr/local/bin/cos\""));
    assert!(!source.contains("pkexec"));
    assert!(!source.contains("approval-helper"));
    assert!(!source.contains("clawd_client::"));
    assert!(!source.contains("zbus::"));
}
