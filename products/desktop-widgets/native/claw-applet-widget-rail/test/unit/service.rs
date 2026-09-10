use super::*;

#[test]
fn translates_all_presented_fields_without_inventing_state() {
    let event = calendar_event(applet::CalendarEvent {
        id: "event-1".into(),
        title: "Review".into(),
        start: "2026-09-08".into(),
        end: Some("2026-09-09".into()),
        location: "Office".into(),
    });
    assert_eq!(event.id, "event-1");
    assert_eq!(event.title, "Review");
    assert_eq!(event.start, "2026-09-08");
    assert_eq!(event.end.as_deref(), Some("2026-09-09"));
    assert_eq!(event.location, "Office");
    let task = task(applet::Task {
        id: "task-1".into(),
        purpose: "Review".into(),
        status: "running".into(),
        created_at: "2026-09-09".into(),
    });
    assert_eq!(
        task,
        Task {
            id: "task-1".into(),
            purpose: "Review".into(),
            status: "running".into(),
            created_at: "2026-09-09".into(),
        }
    );
    let summary = system_summary(applet::SystemSummary {
        cpu_percent: Some(42.0),
        memory: Some(applet::Usage {
            used_mb: 2,
            total_mb: 4,
        }),
        storage: Some(applet::Usage {
            used_mb: 3,
            total_mb: 5,
        }),
        network_down_bps: Some(123),
        network_up_bps: Some(456),
        fallback: true,
    });
    assert_eq!(summary.cpu_percent, Some(42.0));
    assert_eq!(
        summary.memory.unwrap(),
        Usage {
            used_mb: 2,
            total_mb: 4
        }
    );
    assert_eq!(
        summary.storage.unwrap(),
        Usage {
            used_mb: 3,
            total_mb: 5
        }
    );
    assert_eq!(summary.network_down_bps, Some(123));
    assert_eq!(summary.network_up_bps, Some(456));
    assert!(summary.fallback);
}
