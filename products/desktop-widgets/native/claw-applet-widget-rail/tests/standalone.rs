use std::{fs::File, io::Read, process::Command};

#[test]
fn actual_standalone_elf_runs_without_shell_or_desktop_transports() {
    let binary = env!("CARGO_BIN_EXE_claw-applet-widget-rail");
    let mut magic = [0_u8; 4];
    File::open(binary).unwrap().read_exact(&mut magic).unwrap();
    assert_eq!(&magic, b"\x7fELF");
    let result = Command::new(binary)
        .arg("--version")
        .env_clear()
        .output()
        .unwrap();
    assert!(result.status.success(), "{:?}", result.stderr);
    assert_eq!(
        String::from_utf8(result.stdout).unwrap(),
        format!("claw-applet-widget-rail {}\n", env!("CARGO_PKG_VERSION"))
    );
}
