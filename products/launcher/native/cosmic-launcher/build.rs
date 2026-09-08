use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
    let version = env::var("CARGO_PKG_VERSION").expect("CARGO_PKG_VERSION");
    let profile = env::var("PROFILE").unwrap_or_else(|_| "release".to_string());
    let out = PathBuf::from(env::var_os("OUT_DIR").expect("OUT_DIR")).join("config.rs");
    let content = format!(
        "pub const APP_ID: &str = \"com.clawos.Launcher\";\n\
         pub const VERSION: &str = \"{version}\";\n\
         \n\
         pub fn profile() -> &'static str {{ \"{profile}\" }}\n",
    );
    fs::write(&out, content).expect("write generated config.rs");
    println!("cargo:rerun-if-changed=build.rs");
}
