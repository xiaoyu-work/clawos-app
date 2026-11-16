use super::*;

#[test]
fn capture_metadata_keeps_clipboard_cancellation_and_file_distinct_without_opening_paths() {
    let id = "a".repeat(32);
    for (status, cancelled) in [("clipboard", false), ("cancelled", true)] {
        let result = outcome(json!({"version":1,"request_id":id,"status":status}), &id)
            .unwrap()
            .unwrap();
        assert_eq!(result.cancelled, cancelled);
        assert!(result.path.is_empty());
    }
    let path = "/nonexistent-owner-destination/human choice.png";
    let result = outcome(
        json!({"version":1,"request_id":id,"status":"saved","path":path}),
        &id,
    )
    .unwrap()
    .unwrap();
    assert_eq!(result.path, path);
    assert!(!result.cancelled);
    for status in ["pending", "cancelling"] {
        assert!(
            outcome(json!({"version":1,"request_id":id,"status":status}), &id)
                .unwrap()
                .is_none()
        );
    }
    assert!(
        outcome(
            json!({"version":1,"request_id":id,"status":"cleanup_pending"}),
            &id
        )
        .is_err()
    );
}

#[test]
fn capture_does_not_accept_another_request_or_unchecked_gui_success() {
    let id = "a".repeat(32);
    for value in [
        json!({"version":2,"request_id":id,"status":"clipboard"}),
        json!({"version":1,"request_id":"b".repeat(32),"status":"clipboard"}),
        json!({"version":1,"request_id":id,"status":"success","path":"/image.png"}),
        json!({"version":1,"request_id":id,"status":"cancelled","path":"/image.png"}),
        json!({"version":1,"request_id":id,"status":"clipboard","approved":true}),
        json!({"version":1,"request_id":id,"status":"saved","path":"relative"}),
        json!({"version":1,"request_id":id,"status":"saved","path":"/a\nb"}),
        json!({"version":1,"request_id":id,"status":"saved","path":format!("/{}", "x".repeat(4096))}),
    ] {
        assert!(outcome(value, &id).is_err());
    }
}
