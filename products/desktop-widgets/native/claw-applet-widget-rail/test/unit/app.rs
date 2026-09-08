use super::*;

fn task(status: &str, created_at: &str) -> Task {
    Task {
        id: format!("ses_{status}_{created_at}"),
        purpose: status.to_string(),
        status: status.to_string(),
        created_at: created_at.to_string(),
    }
}

#[test]
fn active_tasks_sort_before_recent_tasks() {
    let selected = select_tasks(vec![
        task("done", "2026-08-05T10:00:00Z"),
        task("running", "2026-08-05T08:00:00Z"),
        task("failed", "2026-08-05T11:00:00Z"),
        task("pending", "2026-08-05T09:00:00Z"),
    ]);
    assert_eq!(selected.len(), 4);
    assert_eq!(selected[0].status, "pending");
    assert_eq!(selected[1].status, "running");
    assert_eq!(selected[2].status, "failed");
    assert_eq!(selected[3].status, "done");
}

#[test]
fn suggestions_are_deterministic_from_state() {
    let calendar = SourceState::Empty;
    let tasks = SourceState::Ready(vec![task("running", "2026-08-05T08:00:00Z")]);
    let system = SourceState::Ready(SystemSummary {
        memory: Some(Usage {
            used_mb: 900,
            total_mb: 1000,
        }),
        ..Default::default()
    });
    let result = suggestions(&calendar, &tasks, &system);
    assert_eq!(result.len(), 3);
    assert_eq!(result[0], fl!("suggestion-clear"));
    assert!(result[1].contains('1'));
    assert_eq!(result[2], fl!("suggestion-memory"));
}

#[test]
fn source_completion_only_clears_its_own_in_flight_guard() {
    let (mut rail, _) = <WidgetRail as cosmic::Application>::init(
        cosmic::app::Core::default(),
        Providers::new(
            || Box::pin(async { Ok(Vec::new()) }),
            || Box::pin(async { Ok(Vec::new()) }),
            || Box::pin(async { Ok(SystemSummary::default()) }),
        ),
    );
    let _ = cosmic::Application::update(
        &mut rail,
        Message::CalendarLoaded(Err("timed out".to_string())),
    );
    assert!(!rail.calendar_in_flight);
    assert!(rail.tasks_in_flight);
    assert!(rail.system_in_flight);
}

#[test]
fn formats_event_times_and_rates() {
    assert_eq!(event_time("2026-08-05"), fl!("all-day"));
    let eastern = TimeZone::fixed(jiff::tz::offset(-4));
    assert_eq!(
        event_time_in_zone("2026-08-05T09:30:00Z", eastern.clone()),
        "05:30"
    );
    assert_eq!(
        event_time_in_zone("2026-08-05T09:30:00+02:00", eastern),
        "03:30"
    );
    assert_eq!(format_rate(1536), "2 KB/s");
}

#[test]
fn refreshes_use_independent_providers_and_suppress_overlapping_loads() {
    use std::sync::{Arc, atomic::{AtomicUsize, Ordering}};
    let counts = Arc::new([
        AtomicUsize::new(0), AtomicUsize::new(0), AtomicUsize::new(0),
    ]);
    let calendar = Arc::clone(&counts);
    let tasks = Arc::clone(&counts);
    let system = Arc::clone(&counts);
    let providers = Providers::new(
        move || {
            calendar[0].fetch_add(1, Ordering::SeqCst);
            Box::pin(async { Ok(Vec::new()) })
        },
        move || {
            tasks[1].fetch_add(1, Ordering::SeqCst);
            Box::pin(async { Err("denied".to_string()) })
        },
        move || {
            system[2].fetch_add(1, Ordering::SeqCst);
            Box::pin(async { Ok(SystemSummary::default()) })
        },
    );
    let (mut rail, _) = <WidgetRail as cosmic::Application>::init(cosmic::app::Core::default(), providers);
    let _ = cosmic::Application::update(&mut rail, Message::RefreshFast);
    let _ = cosmic::Application::update(&mut rail, Message::RefreshCalendar);
    assert_eq!(counts.each_ref().map(|count| count.load(Ordering::SeqCst)), [1, 1, 1]);
    let _ = cosmic::Application::update(&mut rail, Message::TasksLoaded(Err("denied".into())));
    assert!(matches!(&rail.tasks, SourceState::Unavailable(error) if error == "denied"));
    let _ = cosmic::Application::update(&mut rail, Message::RefreshFast);
    assert_eq!(counts.each_ref().map(|count| count.load(Ordering::SeqCst)), [1, 2, 1]);
    let _ = cosmic::Application::update(&mut rail, Message::CalendarLoaded(Ok(Vec::new())));
    assert!(matches!(rail.calendar, SourceState::Empty));
    let _ = cosmic::Application::update(&mut rail, Message::SystemLoaded(Ok(SystemSummary::default())));
    assert!(matches!(rail.system, SourceState::Ready(_)));
    let _ = cosmic::Application::update(&mut rail, Message::RefreshCalendar);
    let _ = cosmic::Application::update(&mut rail, Message::RefreshFast);
    assert_eq!(counts.each_ref().map(|count| count.load(Ordering::SeqCst)), [2, 2, 2]);
}

#[tokio::test]
async fn provider_results_preserve_empty_error_and_telemetry_states() {
    let providers = Providers::new(
        || Box::pin(async { Ok(Vec::new()) }),
        || Box::pin(async { Err("capability not granted".into()) }),
        || Box::pin(async { Ok(SystemSummary {
            memory: Some(Usage { used_mb: 900, total_mb: 1000 }),
            fallback: true,
            ..Default::default()
        }) }),
    );
    assert_eq!((providers.calendar)().await, Ok(Vec::new()));
    assert_eq!((providers.tasks)().await, Err("capability not granted".into()));
    let summary = (providers.system)().await.unwrap();
    assert!(summary.fallback);
    assert_eq!(summary.memory.unwrap().percent(), 90);
    assert_eq!(Usage::default().percent(), 0);
}
