use super::*;

fn details(enabled: bool, pending: bool, decision: Option<&str>) -> Value {
    json!({
        "app_id": "audio-manager",
        "trust": "verified",
        "permissions": [{
            "permission_id": "exact-id",
            "declared": {"verb": "sys.observe", "scope": "audio"},
            "capability": null,
            "manageable": true,
            "enabled": enabled,
            "live_granted": false,
            "limitation": null,
        }],
        "pending": if pending { vec![json!({
            "id": "ap-synthetic",
            "verb": "sys.observe",
            "scope": {"kind": "name", "value": "audio"},
            "reason": "Synthetic restoration",
        })] } else { vec![] },
        "recent": decision.map(|state| json!({"id": "ap-synthetic", "state": state})).into_iter().collect::<Vec<_>>(),
        "semantics": "Enabled is not granted",
    })
}

fn selected() -> State {
    State {
        apps: vec!["other-app".into(), "audio-manager".into()],
        selected: Some(1),
        details: Some(serde_json::from_value(details(false, false, None)).unwrap()),
        ..State::default()
    }
}

fn show(state: &mut State, value: Value) {
    let _ = state.update(Message::Loaded(state.epoch, "show".into(), Ok(value)));
}

#[test]
fn restoration_stays_pending_until_os_query_reports_policy_enabled() {
    let mut state = selected();
    let _ = state.update(Message::Change("exact-id".into(), true));
    let _ = state.update(Message::Loaded(
        state.epoch,
        "request".into(),
        Ok(json!({"id": "ap-synthetic", "status": "pending", "enabled": true})),
    ));
    assert!(state.details.is_none());
    assert!(state.busy);
    show(&mut state, details(false, true, None));
    let current = state.details.as_ref().unwrap();
    assert_eq!(current.permissions[0].enabled, Some(false));
    assert_eq!(current.pending.len(), 1);

    show(&mut state, details(false, false, Some("approved")));
    assert_eq!(
        state.details.as_ref().unwrap().permissions[0].enabled,
        Some(false)
    );
    show(&mut state, details(true, false, Some("approved")));
    let current = state.details.as_ref().unwrap();
    assert_eq!(current.permissions[0].enabled, Some(true));
    assert_eq!(current.permissions[0].live_granted, Some(false));
    assert!(current.pending.is_empty());
}

#[test]
fn cancelled_os_authentication_remains_pending_and_denial_never_restores() {
    let mut state = selected();
    show(&mut state, details(false, true, None));
    // Cancelling OS authentication changes no policy or decision in the next query.
    show(&mut state, details(false, true, None));
    let current = state.details.as_ref().unwrap();
    assert_eq!(current.pending.len(), 1);
    assert_eq!(current.permissions[0].enabled, Some(false));
    show(&mut state, details(false, false, Some("denied")));
    let current = state.details.as_ref().unwrap();
    assert!(current.pending.is_empty());
    assert_eq!(current.permissions[0].enabled, Some(false));
    assert_eq!(current.recent[0]["state"], "denied");
}

#[test]
fn failed_transport_and_malformed_queries_never_enable_policy() {
    let mut state = selected();
    let _ = state.update(Message::Change("exact-id".into(), true));
    let _ = state.update(Message::Loaded(
        state.epoch,
        "request".into(),
        Err("synthetic transport failure".into()),
    ));
    assert_eq!(
        state.details.as_ref().unwrap().permissions[0].enabled,
        Some(false)
    );
    assert_eq!(state.error.as_deref(), Some("synthetic transport failure"));
    let _ = state.reload_selected();
    let _ = state.update(Message::Loaded(
        state.epoch,
        "show".into(),
        Err("synthetic query failure".into()),
    ));
    assert!(state.details.is_none());
    show(&mut state, json!({"approved": true}));
    assert!(state.details.is_none());
    assert!(
        state
            .error
            .as_deref()
            .unwrap()
            .contains("Invalid permission state")
    );
}

#[test]
fn cancelled_or_wrong_app_queries_cannot_replace_policy() {
    let mut state = selected();
    let _ = state.reload_selected();
    let previous = state.epoch;
    state.cancel();
    let _ = state.update(Message::Loaded(
        previous,
        "show".into(),
        Ok(details(true, false, None)),
    ));
    assert!(state.details.is_none());
    let mut other = details(true, false, None);
    other["app_id"] = json!("other-app");
    show(&mut state, other);
    assert!(state.details.is_none());
    assert!(state.error.as_deref().unwrap().contains("different App"));
}

#[test]
fn refresh_keeps_the_selected_app_and_requeries_instead_of_using_old_details() {
    let mut state = selected();
    let _ = state.update(Message::Loaded(
        state.epoch,
        "list".into(),
        Ok(json!({
            "apps": [{"app_id": "other-app"}, {"app_id": "audio-manager"}],
            "quarantined": [],
            "truncated": false,
        })),
    ));
    assert_eq!(state.selected, Some(1));
    assert!(state.details.is_none());
    assert!(state.busy);
    show(&mut state, details(false, true, None));
    assert_eq!(state.details.as_ref().unwrap().app_id, "audio-manager");
}

#[test]
fn revocation_keeps_the_existing_change_then_query_flow() {
    let mut state = selected();
    show(&mut state, details(true, false, None));
    let _ = state.update(Message::Change("exact-id".into(), false));
    let _ = state.update(Message::Loaded(
        state.epoch,
        "revoke".into(),
        Ok(json!({"revoked": true, "enabled": false, "restart_required": true})),
    ));
    assert!(state.details.is_none());
    assert!(state.busy);
    show(&mut state, details(false, false, None));
    assert_eq!(
        state.details.as_ref().unwrap().permissions[0].enabled,
        Some(false)
    );
    assert_eq!(
        state.notice,
        Some(crate::fl!("app-permissions-refresh-after-change"))
    );
}

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
