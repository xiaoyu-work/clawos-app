use super::*;

#[tokio::test]
#[ignore = "installed native process fixture provides the fixed OS executable"]
async fn installed_permission_client_uses_closed_environment() {
    assert!(std::env::var_os("CLAW_COS_BIN").is_none());
    assert!(std::env::var_os("COS_MCP_SERVER").is_none());
    assert!(std::env::var_os("COS_SESSION").is_none());
    assert_eq!(std::env::var("PATH").unwrap(), "/usr/sbin:/usr/bin:/sbin:/bin");
    let result = call(json!({"action":"list"})).await.unwrap();
    assert_eq!(result["apps"][0]["app_id"], "audio-manager");
}

#[test]
fn helper_ids_are_bounded_and_cannot_be_arguments() {
    assert!(valid_request_id("ap-123abcd"));
    for id in ["--owner", "ap-../../other", "ap-1;id", "", "other"] {
        assert!(!valid_request_id(id));
    }
    assert!(!valid_request_id(&format!("ap-{}", "a".repeat(128))));
}

#[test]
fn requests_cannot_describe_an_owner_or_approval() {
    let value = request("request", "audio-manager", "exact-manifest-key");
    assert!(value.get("owner_uid").is_none());
    assert!(value.get("session").is_none());
    assert!(value.get("approve").is_none());
    assert_eq!(value["app_id"], "audio-manager");
}

#[tokio::test]
async fn mcp_cannot_invoke_the_fixed_approval_helper() {
    let previous = std::env::var_os("COS_MCP_SERVER");
    unsafe {
        std::env::set_var("COS_MCP_SERVER", "1");
    }
    let result = decide("ap-fixture".into(), true).await;
    unsafe {
        match previous {
            Some(value) => std::env::set_var("COS_MCP_SERVER", value),
            None => std::env::remove_var("COS_MCP_SERVER"),
        }
    }
    assert!(result.unwrap_err().contains("MCP cannot"));
}
