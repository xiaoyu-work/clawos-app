// SPDX-License-Identifier: GPL-3.0-only
//! Regional mutations use the published SDK transport and the OS service only.

use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(tag = "action", rename_all = "snake_case")]
pub enum Change {
    SystemLocale { lang: String, region: String },
    OwnerLanguage { languages: String },
    StaticHostname { hostname: String },
    SystemKeyboard {
        #[serde(flatten)]
        keyboard: Keyboard,
    },
    Timezone { timezone: String },
    Ntp { enabled: bool },
}

#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Keyboard {
    pub layout: String,
    pub model: String,
    pub variant: String,
    pub options: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Status {
    action: String,
    pub locale: Vec<String>,
    pub language: String,
    pub hostname: String,
    pub keyboard: Keyboard,
    pub available_locales: Vec<String>,
}

pub async fn status() -> Result<Status, Failure> {
    let response = claw_os_sdk::cos_call_json_async_with_binary(
        "/usr/local/bin/yu", "regional-settings", "control",
        ["__regional-settings".to_owned(), json_request("status")],
    ).await.map_err(classify)?;
    let status: Status = serde_json::from_value(response)
        .map_err(|error| Failure::Unconfirmed(error.to_string()))?;
    if status.action != "status" || status.locale.len() > 32
        || status.locale.iter().any(|value| value.len() > 256)
        || status.language.len() > 4096 || status.hostname.len() > 64
        || status.keyboard.layout.len() > 256 || status.keyboard.model.len() > 128
        || status.keyboard.variant.len() > 256 || status.keyboard.options.len() > 2048
        || status.available_locales.len() > 4096
        || status.available_locales.iter().any(|locale| locale.len() > 128)
    {
        return Err(Failure::Unconfirmed("invalid OS regional observation".into()));
    }
    Ok(status)
}

fn json_request(action: &str) -> String {
    serde_json::json!({"action":action}).to_string()
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TimeStatus {
    action: String,
    pub timezone: String,
    pub ntp: bool,
    pub can_ntp: bool,
    pub timezones: Vec<String>,
}

pub async fn time_status() -> Result<TimeStatus, Failure> {
    let response = claw_os_sdk::cos_call_json_async_with_binary(
        "/usr/local/bin/yu", "regional-settings", "control",
        ["__regional-settings".to_owned(), json_request("time_status")],
    ).await.map_err(classify)?;
    let status: TimeStatus = serde_json::from_value(response)
        .map_err(|error| Failure::Unconfirmed(error.to_string()))?;
    if status.action != "time_status" || status.timezone.len() > 128
        || status.timezones.len() > 4096
        || status.timezones.iter().any(|name| name.len() > 128 || name.chars().any(char::is_control))
    {
        return Err(Failure::Unconfirmed("invalid OS timezone observation".into()));
    }
    Ok(status)
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Failure {
    Denied(String),
    Review(String),
    Unavailable(String),
    Unconfirmed(String),
}

impl Failure {
    pub fn message(&self) -> String {
        match self {
            Self::Denied(detail) => fl!("regional-settings", "denied", detail = detail.as_str()),
            Self::Review(review) => fl!("regional-settings", "review", review = review.as_str()),
            Self::Unavailable(detail) => {
                fl!("regional-settings", "unavailable", detail = detail.as_str())
            }
            Self::Unconfirmed(detail) => {
                fl!("regional-settings", "unconfirmed", detail = detail.as_str())
            }
        }
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
enum AppliedStatus {
    Applied,
}

#[derive(Deserialize)]
#[serde(tag = "action", rename_all = "snake_case", deny_unknown_fields)]
enum Applied {
    SystemLocale {
        status: AppliedStatus,
        locale: Vec<String>,
    },
    OwnerLanguage {
        status: AppliedStatus,
        language: String,
    },
    StaticHostname {
        status: AppliedStatus,
        hostname: String,
    },
    SystemKeyboard {
        status: AppliedStatus,
        keyboard: Keyboard,
    },
    Timezone {
        status: AppliedStatus,
        timezone: String,
    },
    Ntp {
        status: AppliedStatus,
        enabled: bool,
    },
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReviewRequired {
    status: ReviewStatus,
    system_review_id: String,
}

#[derive(Deserialize)]
enum ReviewStatus {
    #[serde(rename = "system_review_required")]
    Required,
}

pub async fn call(change: Change) -> Result<(), Failure> {
    let response = claw_os_sdk::cos_call_json_async_with_binary(
        "/usr/local/bin/yu",
        "regional-settings",
        "control",
        [
            "__regional-settings".to_owned(),
            serde_json::to_string(&change)
                .map_err(|error| Failure::Unavailable(error.to_string()))?,
        ],
    )
    .await
    .map_err(classify)?;
    decode(&change, response)
}

fn classify(error: claw_os_sdk::BridgeError) -> Failure {
    match error {
        claw_os_sdk::BridgeError::AppError { code, message, .. } if code == "PERMISSION_DENIED" => {
            Failure::Denied(message)
        }
        claw_os_sdk::BridgeError::AppError { code, message, .. }
            if code == "KERNEL_UNAVAILABLE" =>
        {
            Failure::Unavailable(message)
        }
        claw_os_sdk::BridgeError::BinaryNotFound(error) => Failure::Unavailable(error.to_string()),
        other => Failure::Unconfirmed(other.to_string()),
    }
}

fn decode(change: &Change, value: Value) -> Result<(), Failure> {
    if value.to_string().len() > 64 * 1024 {
        return Err(Failure::Unconfirmed(
            "OS response exceeded the regional contract limit".into(),
        ));
    }
    if value.get("status").and_then(Value::as_str) == Some("system_review_required") {
        let review: ReviewRequired = serde_json::from_value(value).map_err(|error| {
            Failure::Unconfirmed(format!("invalid OS review response: {error}"))
        })?;
        let ReviewStatus::Required = review.status;
        if review.system_review_id.is_empty()
            || review.system_review_id.len() > 128
            || !review
                .system_review_id
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
        {
            return Err(Failure::Unconfirmed("invalid OS review reference".into()));
        }
        return Err(Failure::Review(review.system_review_id));
    }
    let response: Applied = serde_json::from_value(value)
        .map_err(|error| Failure::Unconfirmed(format!("invalid OS regional response: {error}")))?;
    let matches = match (change, response) {
        (
            Change::SystemLocale { lang, region },
            Applied::SystemLocale {
                status: AppliedStatus::Applied,
                locale,
            },
        ) => locale_matches(lang, region, &locale),
        (
            Change::OwnerLanguage { languages },
            Applied::OwnerLanguage {
                status: AppliedStatus::Applied,
                language,
            },
        ) => *languages == language,
        (
            Change::StaticHostname { hostname },
            Applied::StaticHostname {
                status: AppliedStatus::Applied,
                hostname: observed,
            },
        ) => *hostname == observed,
        (
            Change::SystemKeyboard { keyboard },
            Applied::SystemKeyboard { status: AppliedStatus::Applied, keyboard: observed },
        ) => *keyboard == observed,
        (Change::Timezone { timezone }, Applied::Timezone { status: AppliedStatus::Applied, timezone: observed }) => *timezone == observed,
        (Change::Ntp { enabled }, Applied::Ntp { status: AppliedStatus::Applied, enabled: observed }) => *enabled == observed,
        _ => false,
    };
    if matches {
        Ok(())
    } else {
        Err(Failure::Unconfirmed(
            "OS response did not confirm the requested change".into(),
        ))
    }
}

fn locale_matches(lang: &str, region: &str, locale: &[String]) -> bool {
    const KEYS: [&str; 10] = [
        "LANG",
        "LC_ADDRESS",
        "LC_IDENTIFICATION",
        "LC_MEASUREMENT",
        "LC_MONETARY",
        "LC_NAME",
        "LC_NUMERIC",
        "LC_PAPER",
        "LC_TELEPHONE",
        "LC_TIME",
    ];
    if locale.len() != KEYS.len() {
        return false;
    }
    KEYS.iter().all(|key| {
        let expected = if *key == "LANG" { lang } else { region };
        locale
            .iter()
            .filter(|value| {
                value
                    .split_once('=')
                    .is_some_and(|(name, value)| name == *key && value == expected)
            })
            .count()
            == 1
    })
}

#[derive(Clone, Debug, Default)]
pub struct Pending {
    generation: u64,
    active: bool,
}

impl Pending {
    pub fn busy(&self) -> bool {
        self.active
    }
    pub fn revision(&self) -> (u64, bool) {
        (self.generation, self.active)
    }
    pub fn begin(&mut self) -> Result<u64, Failure> {
        if self.active {
            return Err(Failure::Unavailable(
                "a regional change is already pending".into(),
            ));
        }
        self.generation = self
            .generation
            .checked_add(1)
            .ok_or_else(|| Failure::Unavailable("restart Settings before another change".into()))?;
        self.active = true;
        Ok(self.generation)
    }
    pub fn complete(&mut self, generation: u64) -> bool {
        if !self.active || self.generation != generation {
            return false;
        }
        self.active = false;
        true
    }
}

pub fn outcome(result: &Result<(), Failure>) -> String {
    match result {
        Ok(()) => fl!("regional-settings", "confirmed"),
        Err(error) => error.message(),
    }
}

#[cfg(test)]
mod tests {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/unit/regional_settings.rs"
    ));
}
