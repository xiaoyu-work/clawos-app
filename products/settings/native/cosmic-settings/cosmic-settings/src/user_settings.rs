// SPDX-License-Identifier: GPL-3.0-only

use crate::regional_settings::Failure;
use serde::Deserialize;
use serde_json::{Value, json};

pub const DEFAULT_ICON_FILE: &str = "/usr/share/pixmaps/faces/pop-robot.png";

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Target {
    pub user: String,
    pub uid: u32,
}

#[derive(Clone, Default, PartialEq, Eq)]
pub struct Password(String);

impl Password {
    pub fn new(value: String) -> Self {
        Self(value)
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }

    pub fn valid(&self) -> bool {
        !self.0.is_empty() && self.0.len() <= 256 && !self.0.chars().any(char::is_control)
    }
}

impl std::fmt::Debug for Password {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("Password([redacted])")
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Change {
    FullName(Target, String),
    Rename(Target, String),
    Icon(Target, String),
    AccountType(Target, bool),
    Password(Target, Password),
    Delete(Target),
    Create {
        user: String,
        full_name: String,
        password: Password,
        administrator: bool,
    },
}

#[derive(Debug)]
pub struct Account {
    pub target: Target,
    pub full_name: String,
    pub administrator: bool,
    pub icon_file: String,
}

#[derive(Deserialize)]
struct Status {
    users: Vec<LocalUser>,
}

#[derive(Deserialize)]
struct LocalUser {
    name: String,
    uid: u32,
    managed: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Reply {
    action: String,
    status: String,
    user: String,
    uid: u32,
    value: Value,
    home: String,
    rollback_supported: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Details {
    full_name: String,
    account_type: String,
    icon_file: String,
}

fn invalid(message: impl Into<String>) -> Failure {
    Failure::Unavailable(message.into())
}

pub(crate) fn valid_name(name: &str) -> bool {
    let mut bytes = name.bytes();
    matches!(bytes.next(), Some(first) if first.is_ascii_lowercase() || first == b'_')
        && name.len() <= 32
        && bytes.all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'_' | b'-')
        })
}

pub(crate) fn valid_full_name(name: &str) -> bool {
    name.len() <= 128 && !name.contains([':', ',']) && !name.chars().any(char::is_control)
}

fn target_args(action: &str, target: &Target) -> Result<Vec<String>, Failure> {
    if !valid_name(&target.user) || !(1000..=60000).contains(&target.uid) {
        return Err(invalid(
            "the selected local account is not a managed name/uid target",
        ));
    }
    Ok(vec![
        "__users".into(),
        action.into(),
        "--user".into(),
        target.user.clone(),
        "--uid".into(),
        target.uid.to_string(),
    ])
}

impl Change {
    pub(crate) fn argv(&self) -> Result<Vec<String>, Failure> {
        let (action, target, option) = match self {
            Self::FullName(target, name) if valid_full_name(name) => {
                ("set-full-name", target, Some(("--full-name", name.clone())))
            }
            Self::Rename(target, name) if valid_name(name) => {
                ("rename-user", target, Some(("--new-name", name.clone())))
            }
            Self::Icon(target, path)
                if path.starts_with('/') && !path.chars().any(char::is_control) =>
            {
                ("set-icon", target, Some(("--icon", path.clone())))
            }
            Self::AccountType(target, administrator) => (
                "set-account-type",
                target,
                Some((
                    "--account-type",
                    if *administrator {
                        "administrator"
                    } else {
                        "standard"
                    }
                    .into(),
                )),
            ),
            Self::Delete(target) => ("delete-user", target, None),
            _ => return Err(invalid("invalid local account change")),
        };
        let mut args = target_args(action, target)?;
        if let Some((flag, value)) = option {
            args.extend([flag.into(), value]);
        } else {
            args.push("--confirm".into());
        }
        Ok(args)
    }

    pub(crate) fn account_request(&self) -> Result<Option<AccountRequest<'_>>, Failure> {
        let (action, user, uid, full_name, administrator, password) = match self {
            Self::Create { user, full_name, administrator, password } => {
                if !valid_full_name(full_name) {
                    return Err(invalid("invalid full name"));
                }
                ("create-user", user.as_str(), None, Some(full_name.as_str()), Some(*administrator), password)
            }
            Self::Password(target, password) if (1000..60000).contains(&target.uid) =>
                ("set-user-password", target.user.as_str(), Some(target.uid), None, None, password),
            Self::Password(..) => return Err(invalid("invalid password reset target")),
            _ => return Ok(None),
        };
        if !valid_name(user) || !password.valid() {
            return Err(invalid("invalid username or password"));
        }
        let input = serde_json::to_vec(&json!({
            "action": action,
            "account": {
                "user": user, "uid": uid, "full_name": full_name,
                "administrator": administrator, "password": password.as_str(),
            },
        })).map_err(|_| invalid("could not encode local account change"))?;
        Ok(Some(AccountRequest { action, user, uid, input }))
    }
}

pub(crate) struct AccountRequest<'a> {
    pub action: &'static str,
    pub user: &'a str,
    pub uid: Option<u32>,
    pub input: Vec<u8>,
}

impl Drop for AccountRequest<'_> {
    fn drop(&mut self) {
        self.input.fill(0);
    }
}

async fn call(args: Vec<String>) -> Result<Value, Failure> {
    claw_os_sdk::cos_call_json_async_with_binary("/usr/local/bin/yu", "users", "control", args)
        .await
        .map_err(bridge_failure)
}

fn bridge_failure(error: claw_os_sdk::BridgeError) -> Failure {
    match error {
            claw_os_sdk::BridgeError::AppError { code, message, .. }
                if code == "PERMISSION_DENIED" =>
            {
                Failure::Denied(message)
            }
            claw_os_sdk::BridgeError::AppError { code, message, .. }
                if code == "KERNEL_UNAVAILABLE" =>
            {
                Failure::Unavailable(message)
            }
            claw_os_sdk::BridgeError::BinaryNotFound(error) => {
                Failure::Unavailable(error.to_string())
            }
            other => Failure::Unconfirmed(other.to_string()),
    }
}

fn reply(action: &str, target: &Target, value: Value, status: &str) -> Result<Reply, Failure> {
    if value.to_string().len() > 64 * 1024 {
        return Err(Failure::Unconfirmed(
            "account response exceeded its limit".into(),
        ));
    }
    let value: Reply = serde_json::from_value(value)
        .map_err(|error| Failure::Unconfirmed(format!("invalid account response: {error}")))?;
    if value.action != action
        || value.status != status
        || value.user != target.user
        || value.uid != target.uid
        || value.rollback_supported
        || !value.home.starts_with('/')
        || value.home.len() > 4096
        || value.home.chars().any(char::is_control)
    {
        return Err(Failure::Unconfirmed(
            "OS did not confirm the requested local account target/action".into(),
        ));
    }
    Ok(value)
}

pub async fn load() -> Result<Vec<Account>, Failure> {
    let value = call(vec!["__users".into(), "status".into()]).await?;
    let status: Status = serde_json::from_value(value)
        .map_err(|error| Failure::Unconfirmed(format!("invalid identity status: {error}")))?;
    let mut accounts = Vec::new();
    for local in status.users.into_iter().filter(|user| user.managed) {
        let target = Target {
            user: local.name,
            uid: local.uid,
        };
        let value = call(target_args("show-user", &target)?).await?;
        let response = reply("show-user", &target, value, "observed")?;
        let details: Details = serde_json::from_value(response.value)
            .map_err(|error| Failure::Unconfirmed(format!("invalid account details: {error}")))?;
        let administrator = match details.account_type.as_str() {
            "standard" => false,
            "administrator" => true,
            _ => {
                return Err(Failure::Unconfirmed(
                    "OS returned an unknown account type".into(),
                ));
            }
        };
        accounts.push(Account {
            target,
            full_name: details.full_name,
            administrator,
            icon_file: details.icon_file,
        });
    }
    Ok(accounts)
}

pub(crate) fn decode(change: &Change, value: Value) -> Result<(), Failure> {
    let args = change.argv()?;
    let (target, expected) = match change {
        Change::FullName(target, name)
        | Change::Rename(target, name)
        | Change::Icon(target, name) => (target, Value::String(name.clone())),
        Change::AccountType(target, administrator) => (
            target,
            Value::String(
                if *administrator {
                    "administrator"
                } else {
                    "standard"
                }
                .into(),
            ),
        ),
        Change::Delete(target) => {
            if value.get("action").and_then(Value::as_str) != Some(args[1].as_str())
                || value.get("user").and_then(Value::as_str) != Some(target.user.as_str())
                || value.get("uid").and_then(Value::as_u64) != Some(u64::from(target.uid))
                || value["state"]["kind"] != "user"
                || value["state"].get("record").is_none()
            {
                return Err(Failure::Unconfirmed(
                    "OS did not confirm the account target/action".into(),
                ));
            }
            let confirmed = value["state"]["present"] == false && value["state"]["record"].is_null();
            return if confirmed {
                Ok(())
            } else {
                Err(Failure::Unconfirmed(
                    "OS did not confirm the account mutation".into(),
                ))
            };
        }
        Change::Create { .. } | Change::Password(..) => return Err(invalid("use the private account request")),
    };
    let response = reply(&args[1], target, value, "applied")?;
    if response.value != expected {
        return Err(Failure::Unconfirmed(
            "account readback differs; refresh before retrying".into(),
        ));
    }
    Ok(())
}
pub async fn apply(change: Change) -> Result<(), Failure> {
    if let Some(request) = change.account_request()? {
        let value = claw_os_sdk::cos_call_json_async_with_stdin_binary(
            "/usr/local/bin/yu", "users", "control",
            ["__system-settings", "--request-stdin"], &request.input,
        ).await.map_err(bridge_failure)?;
        return check_account_reply(request.action, request.user, request.uid, value);
    }
    let value = call(change.argv()?).await?;
    decode(&change, value)
}

pub(crate) fn check_account_reply(action: &str, user: &str, expected_uid: Option<u32>, value: Value) -> Result<(), Failure> {
    let uid = value["uid"].as_u64()
        .and_then(|value| u32::try_from(value).ok())
        .filter(|uid| (1000..60000).contains(uid));
    if value["action"] != action || value["status"] != "applied" || value["user"] != user
        || uid.is_none() || expected_uid.is_some_and(|expected| uid != Some(expected))
    {
        return Err(Failure::Unconfirmed("OS did not confirm the local account change; refresh Users".into()));
    }
    Ok(())
}
