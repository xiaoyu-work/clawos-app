// SPDX-License-Identifier: GPL-3.0-only

use crate::regional_settings::Failure;
use serde::Deserialize;
use serde_json::Value;

pub const DEFAULT_ICON_FILE: &str = "/usr/share/pixmaps/faces/pop-robot.png";

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Target {
    pub user: String,
    pub uid: u32,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Change {
    FullName(Target, String),
    Rename(Target, String),
    Icon(Target, String),
    AccountType(Target, bool),
    Password(Target, String),
    Delete(Target),
    Create {
        user: String,
        full_name: String,
        credential: String,
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

pub(crate) fn valid_credential(reference: &str) -> bool {
    if reference.len() > 256 {
        return false;
    }
    let Some((namespace, name)) = reference.split_once('/') else {
        return false;
    };
    [namespace, name].iter().all(|part| {
        !part.is_empty()
            && part.len() <= 255
            && !part.starts_with('-')
            && part.bytes().all(|byte| {
                byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.' | b':')
            })
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
            Self::Password(target, credential) if valid_credential(credential) => (
                "set-password",
                target,
                Some(("--credential", credential.clone())),
            ),
            Self::Delete(target) => ("delete-user", target, None),
            Self::Create {
                user,
                full_name,
                credential,
                ..
            } if valid_name(user) && valid_full_name(full_name) && valid_credential(credential) => {
                return Ok(vec![
                    "__users".into(),
                    "create-user".into(),
                    "--user".into(),
                    user.clone(),
                    "--full-name".into(),
                    full_name.clone(),
                ]);
            }
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
}

async fn call(args: Vec<String>) -> Result<Value, Failure> {
    claw_os_sdk::cos_call_json_async_with_binary("/usr/local/bin/cos", "users", "control", args)
        .await
        .map_err(|error| match error {
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
        })
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
        Change::Password(target, _) | Change::Delete(target) => {
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
            let record = &value["state"]["record"];
            let confirmed = if matches!(change, Change::Delete(_)) {
                value["state"]["present"] == false && record.is_null()
            } else {
                value["state"]["present"] == true
                    && record["name"] == target.user
                    && record["uid"] == target.uid
            };
            return if confirmed {
                Ok(())
            } else {
                Err(Failure::Unconfirmed(
                    "OS did not confirm the account mutation".into(),
                ))
            };
        }
        Change::Create { .. } => {
            return Err(invalid("creation requires its separate bounded sequence"));
        }
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
    apply_with(change, call).await
}

pub(crate) async fn apply_with<F, T>(change: Change, mut transport: F) -> Result<(), Failure>
where
    F: FnMut(Vec<String>) -> T,
    T: std::future::Future<Output = Result<Value, Failure>>,
{
    let args = change.argv()?;
    if let Change::Create {
        user,
        credential,
        administrator,
        ..
    } = &change
    {
        let value = transport(args).await?;
        let record = &value["state"]["record"];
        let uid = record["uid"]
            .as_u64()
            .and_then(|uid| u32::try_from(uid).ok())
            .filter(|uid| (1000..=60000).contains(uid));
        if value["action"] != "create-user"
            || value["state"]["kind"] != "user"
            || value["state"]["present"] != true
            || record["name"] != *user
            || uid.is_none()
        {
            return Err(Failure::Unconfirmed("account creation may have applied without a matching confirmation; refresh before retrying".into()));
        }
        let target = Target {
            user: user.clone(),
            uid: uid.unwrap(),
        };
        // Each OS mutation has its own grants and outcome. Never delete or retry
        // a partly configured account on an ambiguous or denied response.
        for step in [
            Change::Password(target.clone(), credential.clone()),
            Change::AccountType(target.clone(), *administrator),
            Change::Icon(target, DEFAULT_ICON_FILE.into()),
        ] {
            let args = step.argv()?;
            let stage = args[1].clone();
            let result = match transport(args).await {
                Ok(value) => decode(&step, value),
                Err(error) => Err(error),
            };
            if let Err(error) = result {
                let detail = match error {
                    Failure::Denied(detail)
                    | Failure::Review(detail)
                    | Failure::Unavailable(detail)
                    | Failure::Unconfirmed(detail) => detail,
                };
                return Err(Failure::Unconfirmed(format!(
                    "The account was created, but {stage} was not confirmed. Earlier steps may have applied; no rollback was attempted. Refresh before retrying. {detail}",
                )));
            }
        }
        return Ok(());
    }
    let value = transport(args).await?;
    decode(&change, value)
}
