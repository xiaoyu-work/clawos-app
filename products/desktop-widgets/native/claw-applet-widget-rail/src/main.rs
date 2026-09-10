// SPDX-License-Identifier: GPL-3.0-only

fn main() -> cosmic::iced::Result {
    if std::env::args().skip(1).eq(["--version"]) {
        println!("claw-applet-widget-rail {}", env!("CARGO_PKG_VERSION"));
        return Ok(());
    }
    tracing_subscriber::fmt().with_env_filter("warn").init();
    let _ = tracing_log::LogTracer::init();
    claw_applet_widget_rail::run_installed()
}
