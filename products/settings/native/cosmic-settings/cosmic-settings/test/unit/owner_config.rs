use super::*;

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
