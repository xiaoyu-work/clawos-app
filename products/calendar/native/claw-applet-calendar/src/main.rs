// SPDX-License-Identifier: GPL-3.0-only

fn main() -> Result<(), Box<dyn std::error::Error>> {
    if std::env::var("COS_MCP_SERVER").as_deref() == Ok("1") {
        return claw_applet_calendar::run_mcp();
    }
    if std::env::args().skip(1).eq(["--version"]) {
        println!("claw-applet-calendar {}", env!("CARGO_PKG_VERSION"));
        return Ok(());
    }
    tracing_subscriber::fmt().with_env_filter("warn").init();
    let _ = tracing_log::LogTracer::init();
    claw_applet_calendar::run_installed().map_err(Into::into)
}
