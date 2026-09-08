use ashpd::desktop::screenshot::Screenshot;
use clap::{ArgAction, Parser};
use std::{
    collections::HashMap,
    fs,
    io::{Read, Write},
    os::unix::fs::{MetadataExt, OpenOptionsExt},
    path::PathBuf,
};
use zbus::{Connection, proxy, zvariant::Value};

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
    /// Fixed OS provider protocol: PNG on stdout, empty on cancellation.
    #[clap(long, hide = true, conflicts_with = "save_dir")]
    portal_capture_stdout: bool,
}

#[proxy(assume_defaults = true)]
trait Notifications {
    /// Call the org.freedesktop.Notifications.Notify D-Bus method
    #[allow(clippy::too_many_arguments)]
    fn notify(
        &self,
        app_name: &str,
        replaces_id: u32,
        app_icon: &str,
        summary: &str,
        body: &str,
        actions: &[&str],
        hints: HashMap<&str, &Value<'_>>,
        expire_timeout: i32,
    ) -> zbus::Result<u32>;
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
    portal(true, opts.modal).await
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

async fn portal(interactive: bool, modal: bool) -> Result<CaptureOutcome, CaptureError> {
    let response = Screenshot::request()
        .interactive(interactive)
        .modal(modal)
        .send()
        .await
        .map_err(|e| CaptureError::Portal(format!("failed to send screenshot request: {e}")))?
        .response();

    let response = match response {
        Err(err) => {
            if matches!(
                err,
                ashpd::Error::Response(ashpd::desktop::ResponseError::Cancelled)
            ) {
                return Ok(CaptureOutcome {
                    path: String::new(),
                    cancelled: true,
                });
            }
            return Err(CaptureError::Portal(format!(
                "error taking screenshot: {err}"
            )));
        }
        Ok(response) => response,
    };

    let uri = response.uri();
    let path = match uri.scheme() {
        "file" => {
            let response_path = uri
                .to_file_path()
                .map_err(|_| CaptureError::Other(format!("unsupported response URI '{uri}'")))?;
            response_path.to_string_lossy().to_string()
        }
        "clipboard" => String::new(),
        scheme => {
            return Err(CaptureError::Other(format!(
                "unsupported scheme '{scheme}'"
            )));
        }
    };

    Ok(CaptureOutcome {
        path,
        cancelled: false,
    })
}

fn read_portal_png(path: &str) -> Result<Vec<u8>, CaptureError> {
    const MAX_PNG_BYTES: usize = 64 * 1024 * 1024;
    let file = fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)
        .map_err(|e| CaptureError::Io(format!("open portal image: {e}")))?;
    let metadata = file
        .metadata()
        .map_err(|e| CaptureError::Io(e.to_string()))?;
    if !metadata.is_file()
        || metadata.uid() != unsafe { libc::geteuid() }
        || metadata.nlink() != 1
        || metadata.len() > MAX_PNG_BYTES as u64
    {
        return Err(CaptureError::Io(
            "portal image must be a bounded, owner-owned regular file".into(),
        ));
    }
    let mut bytes = Vec::new();
    file.take((MAX_PNG_BYTES + 1) as u64)
        .read_to_end(&mut bytes)
        .map_err(|e| CaptureError::Io(format!("read portal image: {e}")))?;
    if bytes.len() > MAX_PNG_BYTES || !bytes.starts_with(b"\x89PNG\r\n\x1a\n") {
        return Err(CaptureError::Io(
            "portal returned invalid or oversized PNG data".into(),
        ));
    }
    let current = fs::symlink_metadata(path).map_err(|e| CaptureError::Io(e.to_string()))?;
    if current.dev() != metadata.dev() || current.ino() != metadata.ino() {
        return Err(CaptureError::Io(
            "portal image changed during capture".into(),
        ));
    }
    fs::remove_file(path)
        .map_err(|e| CaptureError::Io(format!("remove consumed portal image: {e}")))?;
    Ok(bytes)
}

async fn capture_stdout(modal: bool) -> Result<(), CaptureError> {
    let result = portal(false, modal).await?;
    if result.cancelled {
        return Ok(());
    }
    if result.path.is_empty() {
        return Err(CaptureError::Other(
            "non-interactive capture cannot use the clipboard".into(),
        ));
    }
    let bytes = read_portal_png(&result.path)?;
    std::io::stdout()
        .lock()
        .write_all(&bytes)
        .map_err(|e| CaptureError::Io(format!("write capture pipe: {e}")))
}

async fn send_notification(path: &str) {
    let connection = Connection::session()
        .await
        .expect("failed to connect to session bus");

    let message = if path.is_empty() {
        fl!("screenshot-saved-to-clipboard")
    } else {
        fl!("screenshot-saved-to")
    };
    let proxy = NotificationsProxy::new(&connection)
        .await
        .expect("failed to create proxy");
    _ = proxy
        .notify(
            &fl!("cosmic-screenshot"),
            0,
            "com.clawos.Screenshot",
            &message,
            path,
            &[],
            HashMap::from([("transient", &Value::Bool(true))]),
            5000,
        )
        .await
        .expect("failed to send notification");
}

//TODO: better error handling
#[tokio::main(flavor = "current_thread")]
async fn main() {
    crate::localize::localize();

    if std::env::var("COS_MCP_SERVER").as_deref() == Ok("1") {
        if let Err(e) = mcp::run().await {
            eprintln!("cosmic-screenshot MCP server exited: {e}");
            std::process::exit(1);
        }
        return;
    }

    let args = Args::parse();

    if args.portal_capture_stdout {
        if let Err(error) = capture_stdout(args.modal).await {
            eprintln!("{error}");
            std::process::exit(1);
        }
        return;
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

    if args.notify {
        send_notification(&outcome.path).await;
    }
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/main.rs"));
}
