use super::*;

#[test]
fn chooser_metadata_must_match_the_request_and_never_implies_content_or_permission() {
    let id = "0123456789abcdef0123456789abcdef";
    assert!(matches!(decode(id, json!({
        "version":1,"request_id":id,"status":"selected","uri":"file:///home/fixture/image.png",
    })).unwrap(), Progress::Selected(_)));
    assert!(matches!(decode(id, json!({
        "version":1,"request_id":id,"status":"cancelled",
    })).unwrap(), Progress::Cancelled));
    for wrong in [
        json!({"version":1,"request_id":"other","status":"selected","uri":"file:///image.png"}),
        json!({"version":1,"request_id":id,"status":"selected","uri":"https://example.invalid/image.png"}),
        json!({"version":1,"request_id":id,"status":"selected","uri":"file:///image.png","read_granted":true}),
        json!({"version":1,"request_id":id,"status":"cleanup_pending"}),
    ] {
        assert!(decode(id, wrong).is_err());
    }
}
