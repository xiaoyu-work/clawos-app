use super::*;

fn entry(transient: bool) -> Entry {
    Entry {
        token: "a".repeat(32),
        notification: Notification::new(
            "Independent sender",
            7,
            "",
            "Popup",
            "<plain> & text",
            vec!["default", "Acknowledge"],
            HashMap::from([("transient", zbus::zvariant::Value::Bool(transient))]),
            0,
        ),
        accepted: false,
        activated: false,
    }
}

#[test]
fn actual_native_card_acceptance_is_ticket_bound_and_not_user_acknowledgement() {
    let mut entries = HashMap::from([(7, entry(false))]);
    assert!(matched(&entries, 7, &"b".repeat(32)).is_err());
    let event = feedback(Input::Presented(7), &mut entries)
        .unwrap()
        .unwrap();
    assert_eq!(event["kind"], "presented");
    assert_eq!(event["token"], "a".repeat(32));
    let card = Card::from_json(event["card"].as_str().unwrap()).unwrap();
    assert_eq!(card.id, 7);
    assert_eq!(
        card.body
            .iter()
            .map(|run| run.text.as_str())
            .collect::<String>(),
        "<plain> & text"
    );
    assert_eq!(card.activation.as_deref(), Some("default"));
    assert!(
        feedback(Input::Presented(7), &mut entries)
            .unwrap()
            .is_none()
    );
    let expired = feedback(Input::Closed(7, CloseReason::Expired), &mut entries)
        .unwrap()
        .unwrap();
    assert_eq!(expired["reason"], "expired");
    assert!(entries.is_empty());
}

#[test]
fn original_activation_close_preserves_ack_and_transient_omits_panel_history() {
    let mut entries = HashMap::from([(7, entry(true))]);
    let event = feedback(Input::Presented(7), &mut entries)
        .unwrap()
        .unwrap();
    assert!(event["card"].is_null());
    let action = feedback(
        Input::Activated {
            token: "compositor-token".into(),
            id: 7,
            action: "default".into(),
        },
        &mut entries,
    )
    .unwrap()
    .unwrap();
    assert_eq!(action["kind"], "activated");
    assert!(action.get("activation_token").is_none());
    let closed = feedback(Input::Closed(7, CloseReason::Dismissed), &mut entries)
        .unwrap()
        .unwrap();
    assert_eq!(closed["reason"], "closed");
    assert!(
        feedback(Input::Closed(7, CloseReason::Dismissed), &mut entries)
            .unwrap()
            .is_none()
    );
    entries.insert(7, entry(false));
    let dismissed = feedback(Input::Closed(7, CloseReason::Dismissed), &mut entries)
        .unwrap()
        .unwrap();
    assert_eq!(dismissed["reason"], "dismissed");
}

#[test]
fn host_commands_are_closed_and_never_accept_owner_bus_or_durable_selectors() {
    let request = json!({"kind":"close","handle":7,"token":"a".repeat(32)});
    serde_json::from_value::<Command>(request.clone()).unwrap();
    for field in [
        "owner_uid",
        "app_id",
        "source",
        "id",
        "socket",
        "path",
        "bus",
        "capabilities",
    ] {
        let mut bad = request.clone();
        bad[field] = json!("forged");
        assert!(serde_json::from_value::<Command>(bad).is_err(), "{field}");
    }
}
