// SPDX-License-Identifier: GPL-3.0-only

use std::{env, fs, path::PathBuf};
use xdgen::{App, Context, FluentString};

fn main() {
    const ID: &str = "com.clawos.AppletClipboard";
    println!("cargo:rerun-if-changed=i18n");
    println!("cargo:rerun-if-changed=data/{ID}.desktop");
    let context = Context::new("i18n/", "desktop_entries").unwrap();
    let app = App::new(FluentString("claw-applet-clipboard"))
        .comment(FluentString("claw-applet-clipboard-comment"))
        .keywords(FluentString("claw-applet-clipboard-keywords"));
    let desktop = app
        .expand_desktop(&format!("data/{ID}.desktop"), &context)
        .unwrap();
    let out = PathBuf::from(env::var_os("OUT_DIR").unwrap());
    let destination = out
        .ancestors()
        .nth(4)
        .expect("Cargo target directory")
        .join("xdgen");
    fs::create_dir_all(&destination).unwrap();
    fs::write(destination.join(format!("{ID}.desktop")), desktop).unwrap();
}
