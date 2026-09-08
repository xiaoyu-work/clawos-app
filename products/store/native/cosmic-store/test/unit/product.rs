use super::*;

#[test]
fn package_names_cannot_be_options_paths_or_launch_uris() {
    for name in ["curl", "python3-venv", "libfoo++", "curl:amd64"] {
        assert!(valid_package_name(name), "{name}");
    }
    for name in ["", "-oApt::Hook=id", "../curl", "a/b", "x\0y", "https://example.test", "a b"] {
        assert!(!valid_package_name(name), "{name}");
        assert!(open(Some(name)).is_err());
    }
    assert!(!valid_package_name(&"x".repeat(256)));
}

#[test]
fn mcp_process_cannot_use_human_filesystem_adapters() {
    let previous = std::env::var_os("COS_MCP_SERVER");
    unsafe { std::env::set_var("COS_MCP_SERVER", "1"); }
    assert!(crate::claw_glue::read_bytes(std::path::Path::new("/not-accessed")).is_err());
    assert!(crate::claw_glue::fs_rm(std::path::Path::new("/not-accessed")).is_err());
    unsafe {
        match previous {
            Some(value) => std::env::set_var("COS_MCP_SERVER", value),
            None => std::env::remove_var("COS_MCP_SERVER"),
        }
    }
}
