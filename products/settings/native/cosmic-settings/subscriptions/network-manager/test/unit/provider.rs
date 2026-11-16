use super::*;

fn fixture() -> Value {
    json!({
        "version":1,"provider":"networkmanager","wifi_enabled":true,"airplane_mode":false,"connectivity":4,
        "profiles":[{"uuid":"c1bd71c6-f69b-4bb7-8fa9-a4a0745b284b","path":"/settings/one","kind":"wifi","name":"Saved alias","ssid":"Café","security":"psk"}],
        "devices":[{"path":"/devices/one","kind":2,"interface":"wlan0","state":100,"active":"/active/one","available":["/settings/one"],"hw_address":"02:00:00:00:00:01","speed":0}],
        "access_points":[{"path":"/ap/one","ssid":"Café","strength":72,"device":"/devices/one","hw_address":"02:00:00:00:00:01","interface":"wlan0","state":100,"security":"psk","secured":true,"wps_push":false}],
        "active":[{"path":"/active/one","uuid":"c1bd71c6-f69b-4bb7-8fa9-a4a0745b284b","name":"Saved alias","kind":"wifi","state":2,"ip_addresses":["192.0.2.12"]}]
    })
}

#[test]
fn owner_network_metadata_retains_ssid_alias_addresses_and_device_binding() {
    let value = fixture();
    let state = state(&value).unwrap();
    assert_eq!(state.known_access_points[0].ssid.as_ref(), "Café");
    assert_eq!(state.wireless_access_points[0].strength, 72);
    let ActiveConnectionInfo::WiFi {
        name, ip_addresses, ..
    } = &state.active_conns[0]
    else {
        panic!("missing Wi-Fi");
    };
    assert_eq!(name, "Café");
    assert_eq!(ip_addresses[0].to_string(), "192.0.2.12");
    let devices = devices(&value).unwrap();
    assert_eq!(devices[0].available_connections[0].id, "Saved alias");
    assert_eq!(
        devices[0]
            .active_connection
            .as_ref()
            .unwrap()
            .0
            .uuid
            .as_ref(),
        "c1bd71c6-f69b-4bb7-8fa9-a4a0745b284b"
    );
}

#[test]
fn missing_or_malformed_provider_metadata_is_never_an_empty_success() {
    let mut value = fixture();
    value["wifi_enabled"] = Value::Null;
    assert!(state(&value).is_err());
    value = fixture();
    value["active"][0]["uuid"] = json!("a-different-profile");
    assert!(state(&value).is_err());
    value = fixture();
    value["access_points"][0]["strength"] = json!(101);
    assert!(state(&value).is_err());
}

#[tokio::test]
async fn password_input_is_rejected_before_provider_or_credential_access() {
    let (mut output, _) = futures::channel::mpsc::channel(1);
    let request = Request::Authenticate {
        ssid: "Café".into(),
        identity: None,
        password: secure_string::SecureString::from("a plaintext password"),
        interface: None,
    };
    let error = execute(&request, &mut output).await.unwrap_err();
    assert!(error.contains("credential reference"));
    validate_reference("network/home").unwrap();
    assert!(validate_reference("network/home/other").is_err());
}
