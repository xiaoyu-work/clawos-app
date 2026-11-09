// SPDX-License-Identifier: GPL-3.0-only

fn main() -> cosmic::iced::Result {
    if std::env::var("COS_MCP_SERVER").is_ok_and(|value| value == "1") {
        if let Err(error) = claw_applet_clipboard::run_mcp() {
            eprintln!("Clipboard History MCP unavailable: {error}");
            std::process::exit(1);
        }
        return Ok(());
    }
    if std::env::args().skip(1).eq(["--version"]) {
        println!("claw-applet-clipboard {}", env!("CARGO_PKG_VERSION"));
        return Ok(());
    }
    tracing_subscriber::fmt().with_env_filter("warn").init();
    let _ = tracing_log::LogTracer::init();
    claw_applet_clipboard::run_installed()
}
