use super::*;

#[test]
fn embedded_modules_are_valid_python_and_cannot_load_app_entrypoints() {
    for source in [FS, RECOLL, DOCUMENT, BRIDGE] {
        let status = Command::new("/usr/bin/python3")
            .args(["-I", "-c", "import ast,sys; ast.parse(sys.argv[1])", source])
            .status().unwrap();
        assert!(status.success());
    }
    let command = command();
    assert_eq!(command.get_program(), "/usr/bin/python3");
    assert_eq!(command.get_args().next().unwrap(), "-I");
    let script = command.get_args().nth(2).unwrap();
    assert!(script
        .to_str()
        .unwrap()
        .contains("sys.path[:0] = ['/usr/lib/cos/python']"));
    assert!(Command::new("/usr/bin/python3")
        .args(["-I", "-c", "import ast,sys; ast.parse(sys.argv[1])"])
        .arg(script).status().unwrap().success());
}
