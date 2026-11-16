use super::*;

#[test]
fn test_can_format_battery_remaining() {
    let cases = [
        (59, "Less than a minute until empty"),
        (300, "5 minutes until empty"),
        (305, "5 minutes until empty"),
        (330, "5 minutes until empty"),
        (360, "6 minutes until empty"),
        (3660, "1 hour and 1 minute until empty"),
        (10800, "3 hours until empty"),
        (969400, "11 days, 5 hours and 16 minutes until empty"),
    ];
    for (actual, expected) in cases {
        let battery = Battery {
            remaining_duration: actual.seconds(),
            is_charging: false,
            ..Default::default()
        };
        assert_eq!(battery.remaining_time(), expected);
    }
}

#[test]
fn root_battery_snapshots_preserve_absence_and_refuse_unavailable_or_invalid_observations() {
    let mut value =
        serde_json::json!({"display_device":{"properties":{"battery.present":false}},"devices":[]});
    assert!(!parse_snapshot(value.clone()).unwrap().battery.is_present);
    value["display_device"]["properties"] = serde_json::json!({
        "battery.present":true,"battery.percentage":72.5,"battery.state":"discharging",
        "battery.time_to_empty":"2.5 hours",
    });
    let battery = parse_snapshot(value.clone()).unwrap().battery;
    assert_eq!(battery.percent, 72.5);
    assert_eq!(
        battery.remaining_time(),
        "2 hours and 30 minutes until empty"
    );
    value["display_device"]["properties"]["battery.percentage"] = serde_json::json!(101);
    assert!(parse_snapshot(value).is_err());
    assert!(
        parse_snapshot(serde_json::json!({"display_device":{"error":"unavailable"},"devices":[]}))
            .is_err()
    );
}
