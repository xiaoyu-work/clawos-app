use super::*;

#[test]
fn mcp_cannot_use_human_ui_mutation_adapter() {
    let previous = std::env::var_os("COS_MCP_SERVER");
    unsafe { std::env::set_var("COS_MCP_SERVER", "1") };
    let mkdir = files::mkdir("/not-accessed/terminal-fixture");
    let write = files::write("/not-accessed/terminal-fixture", "not written");
    unsafe {
        match previous {
            Some(value) => std::env::set_var("COS_MCP_SERVER", value),
            None => std::env::remove_var("COS_MCP_SERVER"),
        }
    }
    assert!(mkdir.unwrap_err().to_string().contains("unavailable in MCP"));
    assert!(write.unwrap_err().to_string().contains("unavailable in MCP"));
}

#[test]
fn launch_rejects_invalid_directory_before_invoking_os() {
    for path in ["", "relative", "/bad\0path"] {
        assert!(open(Some(path)).is_err());
    }
}
