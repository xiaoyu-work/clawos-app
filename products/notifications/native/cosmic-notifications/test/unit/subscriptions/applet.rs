use super::*;
use claw_notification_presentation::proxy::NotificationPresentationProxy;
use cosmic::cosmic_config::ConfigGet;

mod fixture {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/support/presentation.rs"
    ));
}
use fixture::Fixture;

#[tokio::test]
async fn public_client_and_actual_app_server_preserve_preferences_and_bounded_actions() {
    let fixture = Fixture::new();
    let (tx, mut rx) = tokio::sync::mpsc::channel(10);
    let (server, client) = UnixStream::pair().unwrap();
    let server = Builder::socket(server)
        .p2p()
        .server(Guid::generate())
        .unwrap()
        .serve_at(
            claw_notification_presentation::OBJECT_PATH,
            Presentation {
                tx,
                config: fixture.config.clone(),
            },
        )
        .unwrap()
        .build();
    let client = Builder::socket(client).p2p().build();
    let (_server, client) = tokio::try_join!(server, client).unwrap();
    let proxy = NotificationPresentationProxy::new(&client).await.unwrap();
    assert_eq!(proxy.version().await.unwrap(), 1);
    assert_eq!(
        Preferences::from_json(&proxy.preferences().await.unwrap()).unwrap(),
        Preferences::new(false)
    );
    assert_eq!(
        Preferences::from_json(
            &proxy
                .set_preferences(r#"{"version":1,"muted":true}"#,)
                .await
                .unwrap()
        )
        .unwrap(),
        Preferences::new(true)
    );
    assert!(matches!(
        rx.recv().await.unwrap(),
        Input::PresentationPreferencesChanged(Preferences { muted: true, .. })
    ));
    for input in [
        r#"{"version":2,"muted":false}"#,
        r#"{"version":1,"muted":false,"app_id":"special"}"#,
        r#"{"version":1,"muted":false,"capabilities":["ui.notify"]}"#,
        r#"{"version":1,"muted":false,"contract_digest":"printed-value","reviewed":true}"#,
        r#"{"version":1,"muted":false,"permission_choice":"allow","yes":true}"#,
    ] {
        assert!(proxy.set_preferences(input).await.is_err());
        assert!(fixture.config.get::<bool>("do_not_disturb").unwrap());
        assert!(rx.try_recv().is_err());
    }
    assert!(proxy.dismiss(0).await.is_err());
    assert!(proxy.invoke_action(1, &"x".repeat(4097)).await.is_err());
    assert!(rx.try_recv().is_err());
    proxy.dismiss(7).await.unwrap();
    assert!(matches!(
        rx.recv().await.unwrap(),
        Input::AppletDismissed(7)
    ));
    proxy.invoke_action(8, "default").await.unwrap();
    assert!(matches!(
        rx.recv().await.unwrap(),
        Input::AppletActivated { id: 8, .. }
    ));
    std::fs::write(fixture.config_file("do_not_disturb"), "broken").unwrap();
    assert!(proxy.preferences().await.is_err());
    drop(rx);
    assert!(proxy.dismiss(9).await.is_err());
}
