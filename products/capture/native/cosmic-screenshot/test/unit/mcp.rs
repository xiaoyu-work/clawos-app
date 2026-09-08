use super::*;

#[test]
fn capture_arguments_fail_before_any_os_policy_or_capture_request() {
    for input in [
        json!(null),
        json!([]),
        json!({}),
        json!({"save_dir":7}),
        json!({"save_dir":""}),
        json!({"save_dir":"relative"}),
        json!({"save_dir":"~/Pictures"}),
        json!({"save_dir":"/work/\0bad"}),
        json!({"save_dir":format!("/{}", "a".repeat(4096))}),
        json!({"save_dir":"/work/shots","interactive":true}),
        json!({"save_dir":"/work/shots","interactive":"false"}),
        json!({"save_dir":"/work/shots","modal":null}),
        json!({"save_dir":"/work/shots","modal":1}),
        json!({"save_dir":"/work/shots","clipboard":true}),
        json!({"save_dir":"/work/shots","owner_uid":0}),
        json!({"save_dir":"/work/shots","session":"forged"}),
    ] {
        assert!(options(input.clone()).is_err(), "{input}");
    }
    assert_eq!(
        options(json!({"save_dir":"/work/shots"})).unwrap(),
        (PathBuf::from("/work/shots"), true)
    );
    assert_eq!(
        options(json!({"save_dir":"/work/shots","modal":false,"interactive":false})).unwrap(),
        (PathBuf::from("/work/shots"), false)
    );
}
