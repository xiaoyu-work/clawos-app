use super::*;

#[test]
fn sdk_policy_preserves_separate_read_and_write_history_requests() {
    assert_eq!(
        history_permission(HistoryPermission::Read),
        applet::HistoryPermission::Read
    );
    assert_eq!(
        history_permission(HistoryPermission::Write),
        applet::HistoryPermission::Write
    );
}
