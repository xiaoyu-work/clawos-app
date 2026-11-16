use super::*;
use serde_json::json;

fn fixture() -> Value {
    json!({"provider":"bluez","available":true,"errors":[],"adapters":[{
        "name":"hci0","address":"02:00:00:00:00:01","object_path":"/org/bluez/hci0",
        "properties":{"alias":"adapter","powered":false,"discovering":false},
        "devices":[{"address":"02:00:00:00:00:02","alias":"mouse","connected":false,"paired":true,"icon":"input-mouse","battery_percentage":"0x2d (45)"}]
    }]})
}

#[test]
fn root_device_metadata_preserves_adapter_pairing_and_battery_binding() {
    let snapshot = parse(fixture()).unwrap();
    let path = OwnedObjectPath::try_from("/org/bluez/hci0").unwrap();
    assert_eq!(snapshot.adapters[&path].enabled, Active::Disabled);
    let device = snapshot.devices.values().next().unwrap();
    assert_eq!(device.adapter, path);
    assert!(device.paired);
    assert_eq!(device.enabled, Active::Disabled);
    assert_eq!(device.battery.as_deref(), Some("45"));
}

#[test]
fn missing_states_and_partial_inventory_are_not_false_successes() {
    let mut value = fixture();
    value["adapters"][0]["properties"]["powered"] = Value::Null;
    assert!(parse(value).is_err());
    let mut value = fixture();
    value["adapters"][0]["devices"][0]["address"] = json!("not-an-address");
    assert!(parse(value).is_err());
    let mut value = fixture();
    value["errors"] = json!([{"adapter":"02:00:00:00:00:01","error":"unavailable"}]);
    assert!(parse(value).is_err());
}
