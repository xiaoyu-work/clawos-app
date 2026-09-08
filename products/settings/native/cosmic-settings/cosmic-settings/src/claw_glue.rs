// SPDX-License-Identifier: GPL-3.0-only
//
// Human-only Settings adapters over OS policy, snapshots and process services.
// These do not dispatch the Files or Terminal Apps.
//
// Hot-path read-only enumerations (listing `~/.local/share/applications/`,
// scanning font dirs, polling `/proc` via `sysinfo`, …) intentionally
// stay on `std::fs` / `tokio::process` and are flagged at the call site
// with `FIXME(claw)` — funnelling those through a subprocess would be
// far too expensive. See the per-app migration notes for the convention.
//
// `BridgeError::is_denied()` is surfaced as
// `io::ErrorKind::PermissionDenied` so existing error paths (e.g. the
// pkexec fallback patterns in other apps) keep working unchanged.

use std::io;
use std::os::unix::process::ExitStatusExt;
use std::path::Path;
use std::process::{ExitStatus, Output};

use cos_runtime::{BridgeError, ask_claw};
use serde::{Deserialize, Serialize};
use serde_json::json;

fn map_err(err: BridgeError) -> io::Error {
    if err.is_denied() {
        io::Error::new(io::ErrorKind::PermissionDenied, err.to_string())
    } else {
        io::Error::other(err.to_string())
    }
}

fn path_str(p: &Path) -> io::Result<&str> {
    p.to_str().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("non-UTF-8 path cannot cross the bridge: {p:?}"),
        )
    })
}

fn human_ui() -> io::Result<()> {
    if std::env::var("COS_MCP_SERVER").as_deref() == Ok("1") {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied, "human Settings access is unavailable in MCP",
        ));
    }
    Ok(())
}

/// User-intent text write. Mirrors `std::fs::write(path, &str)`.
pub fn write_text(path: &Path, contents: &str) -> io::Result<()> {
    human_ui()?;
    let s = path_str(path)?;
    cos_runtime::filesystem::write(s, contents).map(|_| ()).map_err(map_err)
}

/// Create `path` and any missing parents. Mirrors `std::fs::create_dir_all`.
pub fn mkdir_all(path: &Path) -> io::Result<()> {
    human_ui()?;
    let s = path_str(path)?;
    super::human::query("mkdir", json!({"path": s})).map(|_| ())
}

/// Remove a file or directory. The snapshot-backed adapter is recursive, so this
/// matches both `std::fs::remove_file` and `std::fs::remove_dir_all` call
/// sites — settings only removes individual `.desktop` entries today.
pub fn remove(path: &Path) -> io::Result<()> {
    human_ui()?;
    let s = path_str(path)?;
    super::human::query("remove", json!({"path": s})).map(|_| ())
}

/// Rename / move `src` to `dst`. Mirrors `std::fs::rename`.
pub fn rename(src: &Path, dst: &Path) -> io::Result<()> {
    human_ui()?;
    let s = path_str(src)?;
    let d = path_str(dst)?;
    super::human::query("rename", json!({"path": s, "destination": d})).map(|_| ())
}

/// Spawn a registered process via the controlled OS process service. Equivalent in
/// intent to `Command::new(argv[0]).args(&argv[1..]).spawn()` —
/// the kernel gates the launch and records an audit row.
pub fn start(argv: &[&str]) -> io::Result<()> {
    human_ui()?;
    if argv.is_empty() || argv[0].is_empty() || argv.iter().any(|arg| arg.contains('\0')) {
        return Err(io::Error::new(io::ErrorKind::InvalidInput, "invalid command"));
    }
    let mut args = vec!["proc", "spawn", "--"];
    args.extend_from_slice(argv);
    let result = claw_os_sdk::cos_call_json("proc", "spawn", args).map_err(map_err)?;
    if result["pid"].as_u64().is_none() || result["session_id"].as_str().is_none() {
        return Err(io::Error::other("process service did not confirm registration"));
    }
    Ok(())
}

#[derive(Serialize)]
struct SettingsPageContext<'a> {
    page: &'a str,
    title: &'a str,
}

impl ask_claw::Context for SettingsPageContext<'_> {
    const APP_ID: &'static str = "cosmic-settings";
}

#[derive(Serialize)]
struct SettingsSearchContext<'a> {
    mode: &'static str,
    query: &'a str,
}

impl ask_claw::Context for SettingsSearchContext<'_> {
    const APP_ID: &'static str = "cosmic-settings";
}

pub fn ask_claw_page(page: &str, title: &str) -> Result<(), ask_claw::LaunchError> {
    ask_claw::launch(&SettingsPageContext { page, title })
}

pub fn ask_claw_search(query: &str) -> Result<(), ask_claw::LaunchError> {
    ask_claw::launch(&SettingsSearchContext {
        mode: "search",
        query,
    })
}

/// Run `argv` synchronously and return stdout on a clean exit.
///
/// On a non-zero exit status this returns `io::Error::other(stderr)`,
/// matching the most common consumer pattern in cosmic-settings
/// (queries like `xdg-mime query default …` and `locale -a`).
pub fn run_capture(argv: &[&str], timeout_secs: Option<u32>) -> io::Result<String> {
    let r = run(argv, timeout_secs)?;
    if r.exit_code != 0 {
        let msg = if r.stderr.is_empty() {
            format!("`{}` exited with code {}", argv.join(" "), r.exit_code)
        } else {
            r.stderr
        };
        return Err(io::Error::other(msg));
    }
    Ok(r.stdout)
}

/// Run `argv` synchronously and return a synthesized `std::process::Output`.
///
/// Lets call sites that previously chained `.output().await.apply(map_stderr_output)`
/// keep their existing post-processing helpers (which inspect
/// `output.status` / `output.stderr` directly).
pub fn run_output(argv: &[&str], timeout_secs: Option<u32>) -> io::Result<Output> {
    let r = run(argv, timeout_secs)?;
    let raw = (r.exit_code & 0xff) << 8;
    Ok(Output {
        status: ExitStatus::from_raw(raw),
        stdout: r.stdout.into_bytes(),
        stderr: r.stderr.into_bytes(),
    })
}

#[derive(Deserialize)]
struct RunResult {
    exit_code: i32,
    stdout: String,
    stderr: String,
}

fn run(argv: &[&str], timeout_secs: Option<u32>) -> io::Result<RunResult> {
    human_ui()?;
    let value = super::human::query("run", json!({
        "argv": argv, "timeout": timeout_secs.unwrap_or(300),
    }))?;
    serde_json::from_value(value).map_err(io::Error::other)
}
