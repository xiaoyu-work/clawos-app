//! Fixture-only portal for the real native binary. Never captures a display.

use std::{collections::HashMap, io::Write, path::PathBuf, time::Duration};
use zbus::zvariant::{OwnedObjectPath, OwnedValue, Value};

struct Portal(PathBuf);
struct Notifications(PathBuf);
struct Request;

#[zbus::interface(name = "org.freedesktop.Notifications")]
impl Notifications {
    #[allow(clippy::too_many_arguments)]
    fn notify(
        &self,
        app_name: &str,
        replaces_id: u32,
        app_icon: &str,
        summary: &str,
        body: &str,
        actions: Vec<String>,
        hints: HashMap<String, OwnedValue>,
        expire_timeout: i32,
    ) -> u32 {
        let mut log = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(self.0.join("notification-calls"))
            .unwrap();
        writeln!(
            log,
            "{}",
            serde_json::json!({
                "app_name":app_name, "replaces_id":replaces_id, "app_icon":app_icon,
                "summary":summary, "body":body, "actions":actions, "expire_timeout":expire_timeout,
                "transient":hints.get("transient").and_then(|value| bool::try_from(value).ok()),
            })
        )
        .unwrap();
        1
    }
}

#[zbus::interface(name = "org.freedesktop.portal.Request")]
impl Request {
    fn close(&self) {}
}

#[zbus::interface(name = "org.freedesktop.portal.Screenshot")]
impl Portal {
    #[zbus(property, name = "version")]
    fn version(&self) -> u32 {
        2
    }

    async fn screenshot(
        &self,
        parent_window: &str,
        options: HashMap<String, OwnedValue>,
        #[zbus(header)] header: zbus::message::Header<'_>,
        #[zbus(connection)] connection: &zbus::Connection,
    ) -> zbus::fdo::Result<OwnedObjectPath> {
        let modal = options.get("modal").and_then(|v| bool::try_from(v).ok());
        let interactive = options
            .get("interactive")
            .and_then(|v| bool::try_from(v).ok());
        let mut log = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(self.0.join("portal-calls"))
            .unwrap();
        writeln!(
            log,
            "{}",
            serde_json::json!({
                "modal":modal, "interactive":interactive, "parent_window":parent_window,
            })
        )
        .unwrap();
        let reply: serde_json::Value =
            serde_json::from_slice(&std::fs::read(self.0.join("portal-reply.json")).unwrap())
                .unwrap();
        if reply["fail"].as_bool() == Some(true) {
            return Err(zbus::fdo::Error::Failed("fixture portal failure".into()));
        }
        let token = options
            .get("handle_token")
            .and_then(|v| <&str>::try_from(v).ok())
            .ok_or_else(|| zbus::fdo::Error::InvalidArgs("handle_token missing".into()))?;
        let sender = header
            .sender()
            .unwrap()
            .as_str()
            .trim_start_matches(':')
            .replace('.', "_");
        let path = OwnedObjectPath::try_from(format!(
            "/org/freedesktop/portal/desktop/request/{sender}/{token}"
        ))
        .unwrap();
        connection
            .object_server()
            .at(path.clone(), Request)
            .await
            .unwrap();
        let connection = connection.clone();
        let signal_path = path.clone();
        tokio::spawn(async move {
            tokio::time::sleep(Duration::from_millis(30)).await;
            let code = reply["code"].as_u64().unwrap_or(0) as u32;
            let uri = reply["uri"].as_str().unwrap_or("file:///unused");
            let values = HashMap::from([("uri", Value::from(uri))]);
            connection
                .emit_signal(
                    None::<&str>,
                    signal_path,
                    "org.freedesktop.portal.Request",
                    "Response",
                    &(code, values),
                )
                .await
                .unwrap();
        });
        Ok(path)
    }
}

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let fixture: PathBuf = std::env::args_os()
        .nth(1)
        .ok_or("fixture directory required")?
        .into();
    let _connection = zbus::connection::Builder::session()?
        .name("org.freedesktop.portal.Desktop")?
        .name("org.freedesktop.Notifications")?
        .serve_at("/org/freedesktop/portal/desktop", Portal(fixture.clone()))?
        .serve_at("/org/freedesktop/Notifications", Notifications(fixture))?
        .build()
        .await?;
    println!("ready");
    std::future::pending::<()>().await;
    Ok(())
}
