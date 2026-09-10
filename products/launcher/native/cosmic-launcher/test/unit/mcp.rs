use super::*;

#[test]
fn embedded_backend_uses_isolated_interpreter_and_typed_broker() {
    let command = command();
    assert_eq!(command.get_program(), "/usr/bin/python3");
    let args: Vec<_> = command.get_args().collect();
    assert_eq!(args[0], "-I");
    assert_eq!(args[1], "-c");
    assert!(BACKEND.contains("\"__desktop\", \"launch\""));
    assert!(!BACKEND.contains("\"app\", \"launcher\""));
    assert!(SERVER.contains("App.from_manifest(os.environ[\"COS_APP_MANIFEST\"])"));
    assert!(args[2].to_str().unwrap().contains("os.environ['COS_BIN'] = '/usr/local/bin/cos'"));
    assert!(args[2]
        .to_str()
        .unwrap()
        .contains("sys.path[:0] = ['/usr/lib/cos/python']"));
}

#[test]
fn embedded_python_is_valid_without_loading_live_state() {
    let command = command();
    let script = command.get_args().nth(2).unwrap();
    let status = Command::new("/usr/bin/python3")
        .args(["-I", "-c", "import ast,sys; ast.parse(sys.argv[1])"])
        .arg(script)
        .status()
        .unwrap();
    assert!(status.success());
}
