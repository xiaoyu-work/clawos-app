use super::*;

#[test]
fn mcp_validates_identity_and_confirmation_without_selection_or_endpoint_arguments() {
    use crate::mcp::arguments;
    use serde_json::json;
    let id = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
    arguments("history.list", json!({})).unwrap();
    arguments("history.restore", json!({"identity":id})).unwrap();
    arguments("history.remove", json!({"identity":id})).unwrap();
    arguments("history.clear", json!({"confirm":true})).unwrap();
    for (name, value) in [
        ("history.list", json!({"primary":false})),
        ("history.restore", json!({"identity":"not-a-digest"})),
        ("history.restore", json!({"identity":id, "owner_uid":0})),
        ("history.remove", json!({"identity":id,"program":"/bin/sh"})),
        ("history.clear", json!({})),
        ("history.clear", json!({"confirm":false})),
        ("history.clear", json!({"confirm":"true"})),
        ("clipboard-manager.read", json!({})),
    ] {
        assert!(arguments(name, value).is_err(), "{name}");
    }
}

#[cfg(unix)]
#[tokio::test]
async fn history_uses_public_typed_kernel_decoder_and_no_copyq_or_policy_preflight() {
    use std::{fs, os::unix::fs::PermissionsExt};
    use serde_json::json;
    let root = std::env::current_exe().unwrap().parent().unwrap()
        .join(format!("clipboard-client-fixture-{}", std::process::id()));
    fs::create_dir_all(&root).unwrap();
    let binary = root.join("cos");
    fs::write(&binary, concat!(
        "#!/usr/bin/python3\nimport json,sys\n",
        "args=sys.argv[1:]\nassert args[:4]==['--wire=1','__clipboard','history-list','--deadline']\n",
        "assert len(args)==5 and int(args[4])>0\n",
        "print(json.dumps({'wire_version':1,'ok':True,'data':{'entries':[]}}))\n",
    )).unwrap();
    fs::set_permissions(&binary, fs::Permissions::from_mode(0o755)).unwrap();
    assert_eq!(request(&binary, HistoryAction::List, None, false, None).await.unwrap(), json!({"entries":[]}));
    fs::write(&binary, "#!/bin/sh\nprintf '%s\\n' '{\"wire_version\":1,\"ok\":false,\"code\":\"PERMISSION_DENIED\",\"error\":\"history denied\"}'\nexit 1\n").unwrap();
    assert!(request(&binary, HistoryAction::List, None, false, None).await.unwrap_err().contains("history denied"));
    assert!(request(root.join("missing"), HistoryAction::List, None, false, None).await.is_err());
    fs::remove_dir_all(root).unwrap();
}
