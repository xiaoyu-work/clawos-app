use super::*;

#[test]
fn page_catalog_has_unique_ids_supported_by_default_cli() {
    use clap::{CommandFactory, Parser};
    let command = crate::Args::command();
    let mut ids = std::collections::HashSet::new();
    for (id, label, hint) in PAGES {
        assert!(ids.insert(id));
        assert!(!label.is_empty() && !hint.is_empty());
        assert!(command.get_subcommands().any(|command| command.get_name() == *id), "{id}");
        assert!(crate::Args::try_parse_from(["cosmic-settings", id]).is_ok(), "{id}");
    }
    assert_eq!(ids.len(), 31);
    for page in ["accessibility-magnifier", "dock-applet", "panel-applet"] {
        assert!(valid_page(page), "{page}");
    }
    for page in ["--help", "users;id", "../users", "", "settings://wireless"] {
        assert!(!valid_page(page), "{page}");
    }
}

#[test]
fn mcp_cannot_enter_human_filesystem_or_process_adapters() {
    let previous = std::env::var_os("COS_MCP_SERVER");
    unsafe { std::env::set_var("COS_MCP_SERVER", "1"); }
    let path = std::path::Path::new("/not-accessed");
    assert!(crate::claw_glue::write_text(path, "not-written").is_err());
    assert!(crate::claw_glue::mkdir_all(path).is_err());
    assert!(crate::claw_glue::remove(path).is_err());
    assert!(crate::claw_glue::rename(path, path).is_err());
    assert!(crate::claw_glue::start(&["not-executed"]).is_err());
    assert!(crate::claw_glue::run_capture(&["not-executed"], Some(1)).is_err());
    assert!(crate::claw_glue::run_output(&["not-executed"], Some(1)).is_err());
    assert!(crate::human::query("run", json!({})).is_err());
    unsafe {
        match previous {
            Some(value) => std::env::set_var("COS_MCP_SERVER", value),
            None => std::env::remove_var("COS_MCP_SERVER"),
        }
    }
}
