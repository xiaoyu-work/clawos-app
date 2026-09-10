use super::*;
use claw_notification_presentation::{Icon, MAX_IMAGE_BYTES};
use cosmic_notifications_util::{Hint, Image};

pub(super) mod fixture {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/support/presentation.rs"
    ));
}
use fixture::Fixture;

fn notification() -> Notification {
    Notification {
        id: 7,
        app_name: "Example".into(),
        app_icon: "mail-unread-symbolic".into(),
        summary: "Summary".into(),
        body: "<b>Bold</b><i>Italic</i><u>Underlined</u><a href=\"ignored\">Link</a>".into(),
        actions: vec![
            (ActionId::Custom("other".into()), "Other".into()),
            (ActionId::Default, "Open".into()),
        ],
        hints: vec![],
        expire_timeout: 5000,
        time: std::time::SystemTime::now(),
    }
}

#[test]
fn preserves_product_markup_action_and_icon_precedence() {
    let fixture = Fixture::new();
    let mut source = notification();
    let app_icon = fixture.root.join("app-symbolic.svg");
    std::fs::write(&app_icon, b"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"2\" height=\"1\"><rect width=\"2\" height=\"1\"/></svg>").unwrap();
    source.app_icon = app_icon.to_string_lossy().into_owned();
    source.hints.push(Hint::Image(Image::Data {
        width: 1,
        height: 1,
        data: vec![0, 1, 2, 255],
    }));
    let result = card(&source).unwrap();
    assert_eq!(result.source_label, source.app_name);
    assert_eq!(result.title, source.summary);
    assert_eq!(result.activation.as_deref(), Some("default"));
    assert!(result.body[0].bold);
    assert!(result.body[1].italic);
    assert!(result.body[2].underline);
    assert!(result.body[3].underline && result.body[3].accent);
    assert!(matches!(result.icon, Some(Icon::Rgba { .. })));
    assert!(matches!(result.group_icon, Some(Icon::Mask { .. })));
    assert_eq!(Card::from_json(&result.to_json().unwrap()).unwrap(), result);
    source.actions.remove(1);
    assert_eq!(card(&source).unwrap().activation.as_deref(), Some("other"));
    source.actions.clear();
    assert_eq!(card(&source).unwrap().activation, None);
}

#[test]
fn snapshots_product_image_bytes_and_never_exports_a_host_path() {
    let fixture = Fixture::new();
    let path = fixture.root.join("mail-symbolic.svg");
    let bytes = b"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"2\" height=\"1\"><rect width=\"2\" height=\"1\"/></svg>";
    std::fs::write(&path, bytes).unwrap();
    let mut source = notification();
    source.app_icon = url::Url::from_file_path(&path).unwrap().into();
    let result = card(&source).unwrap();
    assert!(
        matches!(&result.icon, Some(Icon::Mask { width: 128, height: 128, alpha }) if alpha.len() == 128 * 128 && alpha.iter().all(|value| *value == 255))
    );
    assert!(!result.to_json().unwrap().contains(path.to_str().unwrap()));
    std::fs::write(&path, vec![0; MAX_IMAGE_BYTES + 1]).unwrap();
    assert!(card(&source).is_err());
    std::fs::remove_file(&path).unwrap();
    assert!(card(&source).is_err());
    rustix::fs::mkfifoat(
        rustix::fs::CWD,
        &path,
        rustix::fs::Mode::RUSR | rustix::fs::Mode::WUSR,
    )
    .unwrap();
    assert!(
        card(&source).is_err(),
        "non-regular images must not block projection"
    );
}

#[test]
fn changes_only_existing_presentation_mute_without_migrating_product_settings() {
    let fixture = Fixture::new();
    let config = &fixture.config;
    config
        .set("anchor", cosmic_notifications_config::Anchor::BottomLeft)
        .unwrap();
    config.set("max_notifications", 8_u32).unwrap();
    let anchor = std::fs::read(fixture.config_file("anchor")).unwrap();
    let maximum = std::fs::read(fixture.config_file("max_notifications")).unwrap();
    assert_eq!(preferences(config).unwrap(), Preferences::new(false));
    assert_eq!(
        set_preferences(config, r#"{"version":1,"muted":true}"#).unwrap(),
        Preferences::new(true)
    );
    assert_eq!(config.get::<bool>("do_not_disturb").unwrap(), true);
    for input in [
        r#"{"version":2,"muted":false}"#,
        r#"{"version":1,"muted":false,"owner":1000}"#,
        r#"{"version":1,"muted":"false"}"#,
        r#"{"version":1,"muted":false,"max_notifications":0}"#,
    ] {
        assert!(set_preferences(config, input).is_err());
        assert_eq!(config.get::<bool>("do_not_disturb").unwrap(), true);
    }
    assert_eq!(
        anchor,
        std::fs::read(fixture.config_file("anchor")).unwrap()
    );
    assert_eq!(
        maximum,
        std::fs::read(fixture.config_file("max_notifications")).unwrap()
    );
    std::fs::write(fixture.config_file("do_not_disturb"), "not valid").unwrap();
    assert!(preferences(config).is_err());
    assert_eq!(
        std::fs::read_to_string(fixture.config_file("do_not_disturb")).unwrap(),
        "not valid"
    );
}
