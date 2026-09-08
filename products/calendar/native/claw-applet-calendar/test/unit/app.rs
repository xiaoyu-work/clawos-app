use super::*;

#[test]
fn truncates_unicode_without_splitting_code_points() {
    assert_eq!(truncate("hello", 5), "hello");
    assert_eq!(truncate("日程表です", 3), "日程表…");
}

fn provider(day: Date) -> crate::AgendaFuture {
    assert_eq!(day, "2031-11-18".parse::<Date>().unwrap());
    Box::pin(async { Err("capability not granted".into()) })
}

fn applet() -> CalendarApplet {
    use cosmic::Application;
    let (mut applet, _) = CalendarApplet::init(Default::default(), provider);
    applet.calendar.set_selected_visible("2031-11-18".parse().unwrap());
    applet.popup = Some(window::Id::unique());
    applet
}

#[test]
fn selected_day_is_sent_to_the_injected_provider() {
    let mut applet = applet();
    let _ = applet.start_load();
    assert!(applet.loading);
    assert_eq!(applet.refresh_generation, 1);
}

#[test]
fn stale_result_cannot_replace_the_current_agenda() {
    use cosmic::Application;
    let mut applet = applet();
    applet.refresh_generation = 2;
    applet.loading = true;
    let _ = applet.update(Message::Loaded(applet.calendar.selected, 1, Ok(Vec::new())));
    assert!(applet.loading);
    assert!(matches!(applet.agenda, AgendaState::Loading));
}

#[test]
fn denied_provider_result_is_visible_and_does_not_become_empty_success() {
    use cosmic::Application;
    let mut applet = applet();
    let _ = applet.update(Message::Loaded(
        applet.calendar.selected, 0, Err("capability not granted".into()),
    ));
    assert!(matches!(applet.agenda, AgendaState::Unavailable(ref error)
        if error == "capability not granted"));
}

#[test]
fn day_change_while_loading_queues_a_fresh_provider_request() {
    use cosmic::Application;
    let mut applet = applet();
    applet.loading = true;
    applet.pending_day = Some(applet.calendar.selected);
    let _ = applet.update(Message::Loaded(applet.calendar.selected, 0, Ok(Vec::new())));
    assert!(applet.loading);
    assert!(applet.pending_day.is_none());
    assert_eq!(applet.refresh_generation, 1);
}
