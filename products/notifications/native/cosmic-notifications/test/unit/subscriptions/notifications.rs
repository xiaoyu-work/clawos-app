use super::*;

mod fixture {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/support/presentation.rs"
    ));
}

#[test]
fn retired_and_disconnected_handles_are_reclaimed_only_for_their_sender() {
    let (tx, _rx) = channel(10);
    let mut server = Notifications::new(tx);
    let bound = server.allocate(":1.1", 0).unwrap().0;
    let persistent = server.allocate(":1.1", 0).unwrap().0;
    let foreign = server.allocate(":1.2", 0).unwrap().0;
    server.connection_bound.extend([bound, foreign]);
    assert!(server.retire_sender(":1.3").is_empty());
    assert_eq!(server.retire_sender(":1.1"), vec![bound]);
    assert!(
        server.owners.contains_key(&persistent),
        "ordinary freedesktop lifetime is unchanged"
    );
    assert!(server.owners.contains_key(&foreign));
    for _ in 0..5000 {
        let id = server.allocate(":1.4", 0).unwrap().0;
        assert!(
            server.retire(id),
            "evicted presentations must not exhaust the handle bound"
        );
    }
    assert_eq!(server.owners.len(), 2);
}

#[test]
fn numerical_ids_are_sender_bound_not_hints_or_labels() {
    let (tx, _) = channel(10);
    let mut daemon = Notifications::new(tx);
    let (first, replaced) = daemon.allocate(":1.1", 0).unwrap();
    assert!(!replaced);
    assert_eq!(daemon.allocate(":1.1", first).unwrap(), (first, true));
    assert!(daemon.allocate(":1.2", first).is_err());
    let (second, replaced) = daemon.allocate(":1.2", 999).unwrap();
    assert!(!replaced);
    assert_ne!(second, first);
    assert_ne!(second, 999, "unknown replacement ids cannot become aliases");
    daemon.next = NonZeroU32::new(u32::MAX).unwrap();
    daemon.allocate(":1.2", 0).unwrap();
    assert_ne!(daemon.allocate(":1.2", 0).unwrap().0, first);
}

#[tokio::test]
async fn actual_descriptor_handoff_fans_out_legacy_and_generic_presentations() {
    use claw_notification_presentation::{Card, proxy::NotificationPresentationProxy};
    use cosmic::cosmic_config::ConfigSet;
    use futures::StreamExt;
    use std::{os::fd::AsRawFd, time::Duration};

    tokio::time::timeout(Duration::from_secs(10), async {
    let fixture = fixture::Fixture::new();
    fixture.config.set("do_not_disturb", true).unwrap();
    let stored_mute = std::fs::read(fixture.config_file("do_not_disturb")).unwrap();
    let (tx, mut rx) = channel(100);
    let (presenter_fd, panel_fd) = std::os::unix::net::UnixStream::pair().unwrap();
    panel_fd.set_nonblocking(true).unwrap();
    unsafe {
        std::env::set_var(claw_notification_presentation::PRESENTER_FD_ENV,
            presenter_fd.as_raw_fd().to_string());
    }
    let server = applet::setup_panel_conn(tx.clone());
    let client = ConnectionBuilder::socket(
        tokio::net::UnixStream::from_std(panel_fd).unwrap(),
    ).p2p().build();
    let (panel_server, panel_client) = tokio::join!(server, client);
    let _panel_server = panel_server.unwrap();
    let panel_client = panel_client.unwrap();
    let socket = zbus::Proxy::new(
        &panel_client, "com.clawos.NotificationsSocket",
        "/com/clawos/NotificationsSocket", "com.clawos.NotificationsSocket",
    ).await.unwrap();
    let fd: zbus::zvariant::OwnedFd = socket.call("GetFd", &()).await.unwrap();
    let stream = std::os::unix::net::UnixStream::from(std::os::fd::OwnedFd::from(fd));
    stream.set_nonblocking(true).unwrap();
    let applet_client = ConnectionBuilder::socket(
        tokio::net::UnixStream::from_std(stream).unwrap(),
    ).p2p().build().await.unwrap();
    let presentation = NotificationPresentationProxy::new(&applet_client).await.unwrap();
    assert_eq!(presentation.version().await.unwrap(), 1);
    assert!(claw_notification_presentation::Preferences::from_json(
        &presentation.preferences().await.unwrap(),
    ).unwrap().muted);
    let mut cards = presentation.receive_card().await.unwrap();
    let legacy = zbus::Proxy::new(
        &applet_client, "com.clawos.NotificationsApplet",
        "/com/clawos/NotificationsApplet", "com.clawos.NotificationsApplet",
    ).await.unwrap();
    let mut legacy_cards = legacy.receive_signal("Notify").await.unwrap();
    let Input::AppletConn(connection) = rx.recv().await.unwrap() else { panic!("missing applet connection") };
    let mut daemon = Notifications::new(tx);
    daemon.applets.push(connection);
    let request = zbus::Message::method_call("/org/freedesktop/Notifications", "Notify")
        .unwrap().sender(":1.20").unwrap().build(&()).unwrap();
    let id = daemon.notify(
        "Example", 0, "mail-unread-symbolic", "Title", "<b>Body</b>",
        vec!["default", "Open"], HashMap::new(), 5000, request.header(),
    ).await.unwrap();
    let message = tokio::time::timeout(Duration::from_secs(2), cards.next()).await.unwrap().unwrap();
    let card = Card::from_json(message.args().unwrap().payload).unwrap();
    assert_eq!(card.id, id);
    assert_eq!(card.source_label, "Example");
    assert_eq!(card.body[0].text, "Body");
    assert!(card.body[0].bold);
    assert_eq!(card.activation.as_deref(), Some("default"));
    assert!(tokio::time::timeout(Duration::from_secs(2), legacy_cards.next()).await.unwrap().is_some());
    assert!(matches!(rx.recv().await.unwrap(), Input::Notification(notification) if notification.id == id));

    let transient = HashMap::from([("transient", zbus::zvariant::Value::Bool(true))]);
    daemon.notify("Example", 0, "", "Transient", "", vec![], transient, 5000, request.header()).await.unwrap();
    assert!(tokio::time::timeout(Duration::from_millis(30), cards.next()).await.is_err());
    assert!(tokio::time::timeout(Duration::from_millis(30), legacy_cards.next()).await.is_err());
    assert_eq!(stored_mute, std::fs::read(fixture.config_file("do_not_disturb")).unwrap());
    }).await.expect("private presentation handoff timed out");
}
