use super::*;

fn details(enabled: Option<bool>) -> Value {
    json!({
        "app_id": "audio-manager",
        "revision": "test-revision",
        "permissions": [{
            "permission_id": "exact-id",
            "label": "Read sound settings",
            "description": "See connected audio devices.",
            "target": "audio",
            "enabled": enabled,
        }],
    })
}

fn selected() -> State {
    State {
        apps: vec!["other-app".into(), "audio-manager".into()],
        selected: Some(1),
        details: Some(serde_json::from_value(details(Some(false))).unwrap()),
        ..State::default()
    }
}

fn show(state: &mut State, value: Value) {
    let _ = state.update(Message::Loaded(state.epoch, "show_choices".into(), Ok(value)));
}

#[test]
fn allow_reloads_the_saved_choice() {
    let mut state = selected();
    let _ = state.update(Message::Change("exact-id".into(), true));
    let _ = state.update(Message::Loaded(
        state.epoch,
        "allow".into(),
        Ok(json!({"enabled": true})),
    ));
    assert!(state.details.is_none());
    assert!(state.busy);
    show(&mut state, details(Some(true)));
    let current = state.details.as_ref().unwrap();
    assert_eq!(current.permissions[0].enabled, Some(true));
}

#[test]
fn an_unset_choice_is_distinct_from_denial() {
    let mut state = selected();
    show(&mut state, details(None));
    assert_eq!(state.details.as_ref().unwrap().permissions[0].enabled, None);
    show(&mut state, details(Some(false)));
    assert_eq!(state.details.as_ref().unwrap().permissions[0].enabled, Some(false));
}

#[test]
fn failed_transport_and_malformed_queries_never_enable_policy() {
    let mut state = selected();
    let _ = state.update(Message::Change("exact-id".into(), true));
    let _ = state.update(Message::Loaded(
        state.epoch,
        "allow".into(),
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
        "show_choices".into(),
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
        "show_choices".into(),
        Ok(details(Some(true))),
    ));
    assert!(state.details.is_none());
    let mut other = details(Some(true));
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
    show(&mut state, details(Some(false)));
    assert_eq!(state.details.as_ref().unwrap().app_id, "audio-manager");
}

#[test]
fn revocation_keeps_the_existing_change_then_query_flow() {
    let mut state = selected();
    show(&mut state, details(Some(true)));
    let _ = state.update(Message::Change("exact-id".into(), false));
    let _ = state.update(Message::Loaded(
        state.epoch,
        "deny".into(),
        Ok(json!({"enabled": false})),
    ));
    assert!(state.details.is_none());
    assert!(state.busy);
    show(&mut state, details(Some(false)));
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
            "permission_id":"x", "label":"test", "description":"test", "target":"x",
            "enabled":"unknown"
        }))
        .is_err()
    );
    let permission: Permission = serde_json::from_value(json!({
        "permission_id":"x", "label":"test", "description":"test", "target":"x",
        "enabled":null, "live_granted":true
    }))
    .unwrap();
    assert_eq!(permission.enabled, None);
}
