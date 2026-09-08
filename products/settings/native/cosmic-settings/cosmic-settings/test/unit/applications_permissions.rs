use super::*;

#[test]
fn cancellation_rejects_stale_catalog_response() {
    let mut state = State::default();
    state.cancel();
    let _ = state.update(Message::Loaded(
        0,
        "list".into(),
        Ok(json!({
            "apps":[{"app_id":"forged-stale"}], "quarantined":[], "truncated":false
        })),
    ));
    assert!(state.apps.is_empty());
    assert!(!state.busy);
}

#[test]
fn unknown_policy_fields_do_not_become_grants() {
    assert!(
        serde_json::from_value::<Permission>(json!({
            "permission_id":"x", "declared":{}, "manageable":true,
            "enabled":"unknown", "live_granted":true
        }))
        .is_err()
    );
    let permission: Permission = serde_json::from_value(json!({
        "permission_id":"x", "declared":{"scope":{"kind":"from-arg","arg":"path"}},
        "capability":null, "manageable":false, "enabled":null, "live_granted":null,
        "limitation":"Cannot revoke mounted resources"
    }))
    .unwrap();
    assert_eq!(permission.enabled, None);
    assert!(!permission.manageable);
}
