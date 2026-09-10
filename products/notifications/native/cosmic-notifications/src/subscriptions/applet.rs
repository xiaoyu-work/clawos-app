use std::{
    collections::HashMap,
    os::fd::{BorrowedFd, IntoRawFd, RawFd},
};
use tokio::{net::UnixStream, sync::mpsc::Sender};
use tracing::{error, info};
use zbus::{
    Connection, Guid, connection::Builder, interface, object_server::SignalEmitter,
    zvariant::OwnedFd,
};

use super::notifications::Input;

use anyhow::{Result, bail};
use claw_notification_presentation::{PRESENTER_FD_ENV as DAEMON_NOTIFICATIONS_FD, Preferences};
use cosmic::cosmic_config::Config;
use std::os::unix::io::FromRawFd;

pub async fn setup_panel_conn(tx: Sender<Input>) -> Result<Connection> {
    let socket = setup_panel_socket()?;
    let config = crate::presentation::config()?;
    let guid = Guid::generate();
    let conn = tokio::time::timeout(
        tokio::time::Duration::from_secs(1),
        Builder::socket(socket)
            .p2p()
            .server(guid)
            .unwrap()
            .serve_at(
                "/com/clawos/NotificationsSocket",
                NotificationsSocket { tx, config },
            )?
            .build(),
    )
    .await??;

    Ok(conn)
}

/// Creates a non-blocking [`UnixStream`] for communicating with the panel.
///
/// # Safety
///
/// It is assumed that `DAEMON_NOTIFICATIONS_FD` was set to a valid raw file descriptor ID.
pub fn setup_panel_socket() -> Result<UnixStream> {
    let Ok(raw_fd_env_var) = std::env::var(DAEMON_NOTIFICATIONS_FD) else {
        bail!("DAEMON_NOTIFICATIONS_FD is not set.");
    };

    let Ok(raw_fd) = raw_fd_env_var.parse::<RawFd>() else {
        bail!("DAEMON_NOTIFICATIONS_FD is not a valid RawFd.");
    };

    let fd = unsafe { BorrowedFd::borrow_raw(raw_fd).try_clone_to_owned().unwrap() };
    info!("Connecting to daemon on fd {}", raw_fd);

    rustix::io::fcntl_setfd(
        &fd,
        rustix::io::fcntl_getfd(&fd)? | rustix::io::FdFlags::CLOEXEC,
    )?;

    let unix_stream = std::os::unix::net::UnixStream::from(fd);
    unix_stream.set_nonblocking(true)?;

    Ok(UnixStream::from_std(unix_stream)?)
}

pub struct NotificationsSocket {
    pub tx: Sender<Input>,
    config: Config,
}

#[interface(name = "com.clawos.NotificationsSocket")]
impl NotificationsSocket {
    #[zbus(out_args("fd"))]
    async fn get_fd(&self) -> zbus::fdo::Result<OwnedFd> {
        let (mine, theirs) = std::os::unix::net::UnixStream::pair()
            .map_err(|e| zbus::fdo::Error::Failed(e.to_string()))?;
        mine.set_nonblocking(true)
            .map_err(|e| zbus::fdo::Error::Failed(e.to_string()))?;
        theirs
            .set_nonblocking(true)
            .map_err(|e| zbus::fdo::Error::Failed(e.to_string()))?;
        let mine: UnixStream =
            UnixStream::from_std(mine).map_err(|e| zbus::fdo::Error::Failed(e.to_string()))?;

        let guid = Guid::generate();

        let tx_clone = self.tx.clone();
        let config = self.config.clone();
        tokio::spawn(async move {
            let conn = match Builder::socket(mine)
                .p2p()
                .server(guid)
                .unwrap()
                .serve_at(
                    "/com/clawos/NotificationsApplet",
                    NotificationsApplet {
                        tx: tx_clone.clone(),
                    },
                )
                .and_then(|builder| {
                    builder.serve_at(
                        claw_notification_presentation::OBJECT_PATH,
                        Presentation {
                            tx: tx_clone.clone(),
                            config,
                        },
                    )
                }) {
                Ok(conn) => conn,
                Err(err) => {
                    error!("Failed to create applet connection {}", err);
                    return;
                }
            };

            info!("Creating applet connection");
            let conn = match conn.build().await {
                Ok(conn) => conn,
                Err(err) => {
                    error!("Failed to create applet connection {}", err);
                    return;
                }
            };
            info!("Created applet connection");

            if let Err(err) = tx_clone.send(Input::AppletConn(conn)).await {
                error!("Failed to send applet connection {}", err);
                return;
            }
            info!("Sent applet connection");
        });

        let raw = theirs.into_raw_fd();
        info!("Sending fd to applet");

        Ok(unsafe { zbus::zvariant::OwnedFd::from(std::os::fd::OwnedFd::from_raw_fd(raw)) })
    }
}

pub struct NotificationsApplet {
    tx: Sender<Input>,
}

#[interface(name = "com.clawos.NotificationsApplet")]
impl NotificationsApplet {
    pub async fn dismiss(&self, id: u32) -> zbus::fdo::Result<()> {
        self.tx
            .send(Input::AppletDismissed(id))
            .await
            .map_err(|_| zbus::fdo::Error::Failed("notification UI is unavailable".into()))
    }

    #[zbus(signal)]
    pub async fn notify(
        signal_ctxt: &SignalEmitter<'_>,
        app_name: &str,
        replaces_id: u32,
        app_icon: &str,
        summary: &str,
        body: &str,
        actions: Vec<&str>,
        hints: HashMap<&str, zbus::zvariant::Value<'_>>,
        expire_timeout: i32,
    ) -> zbus::Result<()>;

    pub async fn invoke_action(&self, id: u32, action: &str) -> zbus::fdo::Result<()> {
        tracing::trace!("Received action from applet {id} {action}");
        let res = self
            .tx
            .send(Input::AppletActivated {
                id,
                action: action.parse().unwrap(),
            })
            .await;
        if let Err(err) = res {
            tracing::error!("Failed to send action invoke message to channel. {id}");
            return Err(zbus::fdo::Error::Failed(err.to_string()));
        }
        Ok(())
    }
}

pub(super) struct Presentation {
    tx: Sender<Input>,
    config: Config,
}

#[interface(name = "com.clawos.NotificationPresentation1")]
impl Presentation {
    fn version(&self) -> u32 {
        claw_notification_presentation::VERSION
    }

    fn preferences(&self) -> zbus::fdo::Result<String> {
        crate::presentation::preferences(&self.config)
            .and_then(|value| Ok(value.to_json()?))
            .map_err(|error| zbus::fdo::Error::Failed(error.to_string()))
    }

    async fn set_preferences(&self, payload: &str) -> zbus::fdo::Result<String> {
        Preferences::from_json(payload)
            .map_err(|error| zbus::fdo::Error::InvalidArgs(error.to_string()))?;
        let value = crate::presentation::set_preferences(&self.config, payload)
            .map_err(|error| zbus::fdo::Error::Failed(error.to_string()))?;
        self.send(Input::PresentationPreferencesChanged(value.clone()))
            .await?;
        value
            .to_json()
            .map_err(|error| zbus::fdo::Error::Failed(error.to_string()))
    }

    async fn dismiss(&self, id: u32) -> zbus::fdo::Result<()> {
        claw_notification_presentation::validate_handle(id)
            .map_err(|error| zbus::fdo::Error::InvalidArgs(error.to_string()))?;
        self.send(Input::AppletDismissed(id)).await
    }

    async fn invoke_action(&self, id: u32, action: &str) -> zbus::fdo::Result<()> {
        claw_notification_presentation::validate_action(id, action)
            .map_err(|error| zbus::fdo::Error::InvalidArgs(error.to_string()))?;
        self.send(Input::AppletActivated {
            id,
            action: action.parse().unwrap(),
        })
        .await
    }

    #[zbus(signal)]
    pub async fn card(signal_ctxt: &SignalEmitter<'_>, payload: &str) -> zbus::Result<()>;

    #[zbus(signal)]
    pub async fn preferences_changed(
        signal_ctxt: &SignalEmitter<'_>,
        payload: &str,
    ) -> zbus::Result<()>;

    #[zbus(signal)]
    pub async fn failure(signal_ctxt: &SignalEmitter<'_>, message: &str) -> zbus::Result<()>;
}

impl Presentation {
    async fn send(&self, input: Input) -> zbus::fdo::Result<()> {
        tokio::time::timeout(std::time::Duration::from_secs(1), self.tx.send(input))
            .await
            .map_err(|_| {
                zbus::fdo::Error::Failed("notification presentation channel timed out".into())
            })?
            .map_err(|_| {
                zbus::fdo::Error::Failed("notification presentation is unavailable".into())
            })
    }
}

#[cfg(test)]
mod tests {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/unit/subscriptions/applet.rs"
    ));
}
