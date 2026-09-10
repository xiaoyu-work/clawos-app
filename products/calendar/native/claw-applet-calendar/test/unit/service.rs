use super::*;

#[test]
fn sdk_event_preserves_every_original_presentation_field() {
    let event = calendar_event(applet::CalendarEvent {
        id: "event-1".into(),
        title: "Review".into(),
        start: "2026-09-09".into(),
        end: Some("2026-09-10".into()),
        location: "Office".into(),
    });
    assert_eq!(
        event,
        CalendarEvent {
            id: "event-1".into(),
            title: "Review".into(),
            start: "2026-09-09".into(),
            end: Some("2026-09-10".into()),
            location: "Office".into(),
        }
    );
}
