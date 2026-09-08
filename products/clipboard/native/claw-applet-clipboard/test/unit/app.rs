use super::*;
use cosmic::Application;

fn deny(permission: HistoryPermission) -> crate::PolicyFuture {
    Box::pin(async move { Err(format!("Denied {permission:?} history")) })
}

fn deny_write(permission: HistoryPermission) -> crate::PolicyFuture {
    Box::pin(async move {
        match permission {
            HistoryPermission::Read => Ok(()),
            HistoryPermission::Write => Err("Denied Write history".into()),
        }
    })
}

#[tokio::test]
async fn denied_history_operations_never_reach_copyq() {
    assert_eq!(load_history(deny).await.unwrap_err(), "Denied Read history");
    assert_eq!(restore(deny, "fixture".into()).await.unwrap_err(), "Denied Read history");
    assert_eq!(remove(deny, "fixture".into()).await.unwrap_err(), "Denied Read history");
    assert_eq!(clear(deny).await.unwrap_err(), "Denied Write history");
    assert_eq!(restore(deny_write, "fixture".into()).await.unwrap_err(), "Denied Write history");
    assert_eq!(remove(deny_write, "fixture".into()).await.unwrap_err(), "Denied Write history");
}

fn applet() -> ClipboardApplet {
    ClipboardApplet::init(cosmic::app::Core::default(), deny).0
}

#[test]
fn stale_refresh_cannot_replace_current_history_or_release_busy() {
    let mut app = applet();
    app.popup = Some(window::Id::unique());
    app.refresh_generation = 2;
    app.busy = true;
    let _ = app.update(Message::Loaded(1, Err("stale".into())));
    assert!(app.busy);
    assert!(matches!(app.history, HistoryState::Ready(ref values) if values.is_empty()));
    let _ = app.update(Message::Loaded(2, Err("permission denied".into())));
    assert!(!app.busy);
    assert!(matches!(app.history, HistoryState::Unavailable(ref error) if error == "permission denied"));
}

#[test]
fn close_discards_history_and_inflight_result() {
    let mut app = applet();
    let id = window::Id::unique();
    app.popup = Some(id);
    app.busy = true;
    app.confirm_clear = true;
    app.notice = Some("fixture".into());
    let _ = app.update(Message::CloseRequested(id));
    assert!(app.popup.is_none());
    assert!(!app.confirm_clear);
    assert!(app.notice.is_none());
    let _ = app.update(Message::Loaded(0, Ok(vec![ClipboardEntry {
        identity: "synthetic".into(), preview: "fixture".into(), copied_at: None,
    }])));
    assert!(!app.busy);
    assert!(matches!(app.history, HistoryState::Ready(ref values) if values.is_empty()));
    assert_eq!(app.refresh_generation, 1);
}

#[test]
fn clear_confirmation_and_busy_guards_are_preserved() {
    let mut app = applet();
    let _ = app.update(Message::AskClear);
    assert!(app.confirm_clear);
    let _ = app.update(Message::CancelClear);
    assert!(!app.confirm_clear);
    app.busy = true;
    let _ = app.update(Message::AskClear);
    let _ = app.update(Message::ConfirmClear);
    let _ = app.update(Message::Restore("fixture".into()));
    let _ = app.update(Message::Delete("fixture".into()));
    assert!(!app.confirm_clear);
    assert_eq!(app.refresh_generation, 0);
}
