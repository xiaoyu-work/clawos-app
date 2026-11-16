use cosmic::{Element, iced::Length, widget};
use cosmic_settings_page::Entity;
use serde_json::{Value, json};

#[derive(Debug, Clone)]
pub enum Message {
    Loaded(Result<Value, String>),
    Saved(Result<(), String>),
    Field(&'static str, String),
    Autoconnect(bool),
    Save,
    Cancel,
}

#[derive(Debug)]
pub(super) struct Editor {
    pub return_page: Entity,
    pub busy: bool,
    pub error: Option<String>,
    original: Value,
    name: String,
    interface: String,
    method: String,
    addresses: String,
    gateway: String,
    dns: String,
    ssid: String,
    security: String,
    identity: String,
    username: String,
    autoconnect: bool,
}
impl Editor {
    pub fn new(kind: &str, return_page: Entity, busy: bool) -> Self {
        Self {
            return_page,
            busy,
            error: None,
            original: json!({"kind":kind}),
            name: String::new(),
            interface: String::new(),
            method: "auto".into(),
            addresses: String::new(),
            gateway: String::new(),
            dns: String::new(),
            ssid: String::new(),
            security: "open".into(),
            identity: String::new(),
            username: String::new(),
            autoconnect: true,
        }
    }
    pub fn update(&mut self, message: Message) {
        match message {
            Message::Loaded(Ok(value)) => {
                let field = |key| value[key].as_str().unwrap_or_default().to_string();
                self.name = field("name");
                self.interface = field("interface");
                self.method = field("ipv4_method");
                self.gateway = field("ipv4_gateway");
                self.ssid = field("ssid");
                self.security = field("security");
                self.identity = field("identity");
                self.username = field("username");
                self.addresses = list(&value["ipv4_addresses"]);
                self.dns = list(&value["ipv4_dns"]);
                self.autoconnect = value["autoconnect"].as_bool().unwrap_or(false);
                self.original = value;
                self.busy = false;
            }
            Message::Loaded(Err(error)) | Message::Saved(Err(error)) => {
                self.error = Some(error);
                self.busy = false;
            }
            Message::Field(field, value) => {
                let target = match field {
                    "name" => &mut self.name,
                    "interface" => &mut self.interface,
                    "method" => &mut self.method,
                    "addresses" => &mut self.addresses,
                    "gateway" => &mut self.gateway,
                    "dns" => &mut self.dns,
                    "ssid" => &mut self.ssid,
                    "security" => &mut self.security,
                    "identity" => &mut self.identity,
                    "username" => &mut self.username,
                    _ => return,
                };
                *target = value;
            }
            Message::Autoconnect(value) => self.autoconnect = value,
            _ => {}
        }
    }
    pub fn request(&self) -> Result<Value, String> {
        if self.name.trim().is_empty() {
            return Err(fl!("os-network-name-required"));
        }
        let mut value = self.original.clone();
        value["name"] = json!(self.name);
        value["interface"] = optional(&self.interface);
        value["autoconnect"] = json!(self.autoconnect);
        value["ipv4_method"] = json!(self.method.trim());
        value["ipv4_addresses"] = json!(parts(&self.addresses));
        value["ipv4_gateway"] = optional(&self.gateway);
        value["ipv4_dns"] = json!(parts(&self.dns));
        if value["kind"] == "wifi" {
            value["ssid"] = json!(self.ssid);
            value["security"] = json!(self.security.trim());
            value["identity"] = optional(&self.identity);
        }
        if value["kind"] == "vpn" {
            value["username"] = optional(&self.username);
        }
        Ok(value)
    }
    pub fn view(&self) -> Element<'_, Message> {
        fn field<'a>(label: String, value: &'a str, name: &'static str) -> Element<'a, Message> {
            widget::text_input(label, value)
                .on_input(move |value| Message::Field(name, value))
                .into()
        }
        let mut column = widget::column([])
            .spacing(8)
            .push(field(fl!("os-network-name"), &self.name, "name"))
            .push(field(
                fl!("os-network-interface"),
                &self.interface,
                "interface",
            ))
            .push(
                widget::toggler(self.autoconnect)
                    .label(fl!("os-network-autoconnect"))
                    .on_toggle(Message::Autoconnect),
            )
            .push(field(fl!("os-network-ipv4-method"), &self.method, "method"))
            .push(field(
                fl!("os-network-addresses"),
                &self.addresses,
                "addresses",
            ))
            .push(field(fl!("os-network-gateway"), &self.gateway, "gateway"))
            .push(field(fl!("os-network-dns"), &self.dns, "dns"));
        if self.original["kind"] == "wifi" {
            column = column
                .push(field(fl!("network-name"), &self.ssid, "ssid"))
                .push(field(
                    fl!("os-network-security"),
                    &self.security,
                    "security",
                ))
                .push(field(fl!("identity"), &self.identity, "identity"));
        }
        if self.original["kind"] == "vpn" {
            column = column.push(field(fl!("identity"), &self.username, "username"));
        }
        if let Some(error) = &self.error {
            column = column.push(widget::text(error));
        }
        widget::dialog()
            .title(fl!("os-network-profile"))
            .control(widget::scrollable(column).height(Length::Fixed(430.0)))
            .primary_action(
                widget::button::suggested(fl!("os-network-save"))
                    .on_press_maybe((!self.busy).then_some(Message::Save)),
            )
            .secondary_action(widget::button::standard(fl!("cancel")).on_press(Message::Cancel))
            .into()
    }
}
fn parts(value: &str) -> Vec<&str> {
    value
        .split([',', ' '])
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .collect()
}
fn optional(value: &str) -> Value {
    if value.trim().is_empty() {
        Value::Null
    } else {
        json!(value.trim())
    }
}
fn list(value: &Value) -> String {
    value
        .as_array()
        .map(|values| {
            values
                .iter()
                .filter_map(Value::as_str)
                .collect::<Vec<_>>()
                .join(", ")
        })
        .unwrap_or_default()
}
