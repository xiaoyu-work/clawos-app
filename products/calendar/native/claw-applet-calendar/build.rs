// SPDX-License-Identifier: GPL-3.0-only

use std::{env, fs, path::PathBuf};
use xdgen::{App, Context, FluentString};

fn main() {
    const ID: &str = "com.clawos.PanelCalendarButton";
    println!("cargo:rerun-if-changed=i18n");
    println!("cargo:rerun-if-changed=data/{ID}.desktop");
    let context = Context::new("i18n/", "desktop_entries").unwrap();
    let app = App::new(FluentString("claw-applet-calendar"))
        .comment(FluentString("claw-applet-calendar-comment"))
        .keywords(FluentString("claw-applet-calendar-keywords"));
    let desktop = app
        .expand_desktop(&format!("data/{ID}.desktop"), &context)
        .unwrap();
    // OUT_DIR also follows --target-dir, unlike reading CARGO_TARGET_DIR alone.
    let out = PathBuf::from(env::var_os("OUT_DIR").unwrap());
    let destination = out
        .ancestors()
        .nth(4)
        .expect("Cargo target directory")
        .join("xdgen");
    fs::create_dir_all(&destination).unwrap();
    fs::write(destination.join(format!("{ID}.desktop")), desktop).unwrap();
}
