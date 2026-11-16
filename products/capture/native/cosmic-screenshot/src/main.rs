use clap::{ArgAction, Parser};
use std::{fs, path::PathBuf};

mod gui;
mod localize;
mod mcp;

#[derive(Parser, Default, Debug, Clone, PartialEq, Eq)]
#[command(version, about, long_about = None)]
struct Args {
    /// Enable interactive mode in the portal
    #[clap(long,
        default_missing_value("true"),
        default_value("true"),
        num_args(0..=1),
        require_equals(true),
        action = ArgAction::Set)]
    interactive: bool,
    /// Enable modal mode in the portal
    #[clap(long,
        default_missing_value("true"),
        default_value("true"),
        num_args(0..=1),
        require_equals(true),
        action = ArgAction::Set,)]
    modal: bool,
    /// Send a notification with the path to the saved screenshot
    #[clap(long,
        default_missing_value("true"),
        default_value("true"),
        num_args(0..=1),
        require_equals(true),
        action = ArgAction::Set)]
    notify: bool,
    /// The directory to save the screenshot to, if not performing an interactive screenshot
    #[clap(short, long)]
    save_dir: Option<PathBuf>,
    /// Retired private provider mode; capture helpers belong to the OS.
    #[clap(long, hide = true, conflicts_with = "save_dir")]
    portal_capture_stdout: bool,
}

/// Options that drive a single screenshot capture, shared by CLI and
/// MCP entry points so both flows take the same code path.
#[derive(Debug, Clone)]
pub(crate) struct CaptureOptions {
    pub interactive: bool,
    pub modal: bool,
    pub save_dir: Option<PathBuf>,
}

/// Outcome of a successful capture. `path` is empty when the portal
/// chose to put the image on the clipboard instead of writing a file.
#[derive(Debug, Clone)]
pub(crate) struct CaptureOutcome {
    pub path: String,
    pub cancelled: bool,
}

#[derive(Debug)]
pub(crate) enum CaptureError {
    /// The portal returned an error other than "user cancelled".
    Portal(String),
    /// We couldn't move/rename the temp file to `save_dir`.
    Io(String),
    /// Anything else (URI scheme we don't model, etc.).
    Other(String),
}

impl std::fmt::Display for CaptureError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CaptureError::Portal(s) | CaptureError::Io(s) | CaptureError::Other(s) => {
                f.write_str(s)
            }
        }
    }
}

pub(crate) async fn capture(opts: CaptureOptions) -> Result<CaptureOutcome, CaptureError> {
    if !opts.interactive {
        let dir = opts
            .save_dir
            .or_else(dirs::picture_dir)
            .ok_or_else(|| CaptureError::Io("failed to locate picture directory".into()))?;
        if !dir.is_dir() {
            return Err(CaptureError::Io(format!(
                "screenshot destination is not an existing directory: {}",
                dir.display()
            )));
        }
        let dir = fs::canonicalize(dir).map_err(|e| CaptureError::Io(e.to_string()))?;
        return noninteractive(dir, opts.modal, true).await;
    }
    gui::capture(opts.modal).await
}

pub(crate) async fn noninteractive(
    dir: PathBuf,
    modal: bool,
    human_cli: bool,
) -> Result<CaptureOutcome, CaptureError> {
    let dir = dir
        .to_str()
        .ok_or_else(|| CaptureError::Io("directory must be UTF-8".into()))?
        .to_owned();
    let result = tokio::task::spawn_blocking(move || {
        if human_cli {
            cos_runtime::capture::screenshot_from_terminal(&dir, modal)
        } else {
            cos_runtime::capture::screenshot(&dir, modal)
        }
    })
    .await
    .map_err(|e| CaptureError::Other(format!("capture service worker: {e}")))?
    .map_err(|e| CaptureError::Other(format!("OS capture service: {e}")))?;
    Ok(CaptureOutcome {
        path: result.path.unwrap_or_default(),
        cancelled: result.cancelled,
    })
}

async fn send_notification(path: &str) -> Result<(), CaptureError> {
    let message = if path.is_empty() {
        fl!("screenshot-saved-to-clipboard")
    } else {
        fl!("screenshot-saved-to")
    };
    gui::notify(fl!("cosmic-screenshot"), message, path.to_string()).await
}

//TODO: better error handling
#[tokio::main(flavor = "current_thread")]
async fn main() {
    if std::env::var("COS_MCP_SERVER").as_deref() == Ok("1") {
        crate::localize::localize();
        if let Err(e) = mcp::run().await {
            eprintln!("cosmic-screenshot MCP server exited: {e}");
            std::process::exit(1);
        }
        return;
    }

    let args = Args::parse_from(claw_app_gui_argv::normalize(
        std::env::args_os(),
        claw_os_sdk::gui::is_gui_launch(),
        std::ffi::OsStr::new("--gui"),
    ));

    crate::localize::localize();

    if args.portal_capture_stdout {
        eprintln!("private Capture pipe mode is OS-owned; use the authenticated capture service");
        std::process::exit(1);
    }

    let outcome = match capture(CaptureOptions {
        interactive: args.interactive,
        modal: args.modal,
        save_dir: args.save_dir.clone(),
    })
    .await
    {
        Ok(o) => o,
        Err(e) => {
            eprintln!("{e}");
            std::process::exit(1);
        }
    };

    if outcome.cancelled {
        println!("Screenshot cancelled by user");
        std::process::exit(0);
    }

    println!("{}", outcome.path);

    if args.notify
        && let Err(error) = send_notification(&outcome.path).await
    {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/main.rs"));
}
