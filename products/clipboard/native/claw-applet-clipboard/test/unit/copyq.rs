use super::*;
use serde_json::json;

const ID: &str = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";

#[test]
fn accepts_only_bounded_os_history_previews_without_local_copyq_fallback() {
    let value = json!({"entries":[{"identity":ID,"preview":"private <text>","copied_at":"123"}]});
    let entries = snapshot(value).unwrap();
    assert_eq!(entries[0].identity, ID);
    assert_eq!(entries[0].preview, "private <text>");
    for value in [
        json!([]),
        json!({"entries":[{"identity":"bad","preview":"text","copied_at":null}]}),
        json!({"entries":[{"identity":ID,"preview":"x".repeat(182),"copied_at":null}]}),
        json!({"entries":[{"identity":ID,"preview":"bad\u{0}text","copied_at":null}]}),
        json!({"entries":vec![json!({"identity":ID,"preview":"text","copied_at":null});21]}),
    ] {
        assert!(snapshot(value).is_err());
    }
}

#[test]
fn action_results_require_exact_positive_os_confirmation() {
    outcome(json!({"restored":true}), "restored").unwrap();
    outcome(json!({"removed":true}), "removed").unwrap();
    outcome(json!({"cleared":true}), "cleared").unwrap();
    assert!(outcome(json!({"restored":false}), "restored").is_err());
    assert!(outcome(json!({"removed":true}), "restored").is_err());
    assert!(outcome(json!({"restored":true,"other":true}), "restored").is_err());
}
