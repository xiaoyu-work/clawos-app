use super::*;

#[tokio::test]
#[ignore = "installed native process fixture provides the fixed OS executable"]
async fn installed_permission_client_uses_closed_environment() {
    assert!(std::env::var_os("CLAW_COS_BIN").is_none());
    assert!(std::env::var_os("COS_MCP_SERVER").is_none());
    assert!(std::env::var_os("COS_SESSION").is_none());
    assert_eq!(
        std::env::var("PATH").unwrap(),
        "/usr/sbin:/usr/bin:/sbin:/bin"
    );
    let result = call(json!({"action":"list"})).await.unwrap();
    assert_eq!(result["apps"][0]["app_id"], "audio-manager");
}

#[test]
fn requests_cannot_describe_an_owner_or_approval() {
    for action in ["request", "revoke"] {
        let value = request(action, "audio-manager", "exact-manifest-key");
        assert_eq!(
            value,
            json!({
                "action": action,
                "app_id": "audio-manager",
                "permission_id": "exact-manifest-key",
                "reason": "Restore this declared App permission, subject to the existing OS launch and capability ceilings.",
            })
        );
    }
}
