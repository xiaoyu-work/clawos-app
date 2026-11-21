//! Presentation/correlation only. Root owns consent, execution and completion.

use std::{
    fs::{self, OpenOptions},
    io::{self, Read, Write},
    path::PathBuf,
};

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::{Operation, OperationKind, backend::BackendName};

const HISTORY_LIMIT: usize = 128;
const INTENT_BYTES: u64 = 64 * 1024;
pub const FLATPAK_UNAVAILABLE: &str =
    "OS_PACKAGE_PROVIDER_UNSUPPORTED: Only exact Flatpak installs and updates from configured \
     signed sources are supported here. Use the system administrator's Flatpak tools for \
     source changes, local bundles and removals.";

#[derive(Clone, Copy, Debug, Deserialize, Eq, Hash, PartialEq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum Action {
    Install,
    InstallRelease,
    FlatpakInstall,
    FlatpakUpdate,
    Remove,
    Purge,
    Upgrade,
}

impl Action {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Install => "install",
            Self::InstallRelease => "install-release",
            Self::FlatpakInstall => "flatpak-install",
            Self::FlatpakUpdate => "flatpak-update",
            Self::Remove => "remove",
            Self::Purge => "purge",
            Self::Upgrade => "upgrade",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Mode {
    Review,
    Submit,
    Status,
    Recover,
}

impl Mode {
    fn as_str(self) -> &'static str {
        match self {
            Self::Review => "review",
            Self::Submit => "submit",
            Self::Status => "status",
            Self::Recover => "recover",
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Intent {
    pub invocation_id: String,
    pub action: Action,
    pub packages: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub version: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub flatpak: Option<FlatpakTarget>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct FlatpakTarget {
    pub(crate) scope: String,
    pub(crate) remote: String,
    #[serde(rename = "ref")]
    pub(crate) reference: String,
}

impl Intent {
    pub fn for_operation(op: &Operation) -> io::Result<Self> {
        if op.backend_name != BackendName::Packagekit && !op.backend_name.is_flatpak() {
            return Err(io::Error::other("The OS Store supports Debian and Flatpak packages"));
        }
        if op.infos.iter().any(|info| !info.package_paths.is_empty()) {
            return Err(io::Error::other(
                "OS_PACKAGE_SOURCE_UNSUPPORTED: local package archives cannot use the retained \
                 authenticated APT-channel service. Select a package from an OS-configured \
                 authenticated repository; no install-files or PackageKit fallback was attempted.",
            ));
        }
        let version = match op.infos.as_slice() {
            [info] if info.source_id == super::claw_apps::SOURCE_ID
                && matches!(op.kind, OperationKind::Install | OperationKind::Update) =>
            {
                Some(info.releases.first().ok_or_else(|| io::Error::other(
                    "The official App has no authenticated release version"))?.version.clone())
            }
            _ => None,
        };
        let flatpak = if op.backend_name.is_flatpak() {
            let [info] = op.infos.as_slice() else {
                return Err(io::Error::other("Select one exact Flatpak application"));
            };
            let [reference] = info.flatpak_refs.as_slice() else {
                return Err(io::Error::other("The selected source does not provide one exact application ref"));
            };
            let (scope, remote) = if op.backend_name == BackendName::FlatpakUser {
                ("user", info.source_id.as_str())
            } else {
                ("system", info.source_id.strip_suffix(" (system)").ok_or_else(|| io::Error::other("Missing system Flatpak remote"))?)
            };
            Some(FlatpakTarget { scope: scope.into(), remote: remote.into(), reference: reference.clone() })
        } else { None };
        let action = match op.kind {
            OperationKind::Install if flatpak.is_some() => Action::FlatpakInstall,
            OperationKind::Update if flatpak.is_some() => Action::FlatpakUpdate,
            _ if flatpak.is_some() => return Err(io::Error::other(FLATPAK_UNAVAILABLE)),
            OperationKind::Install | OperationKind::Update if version.is_some() => Action::InstallRelease,
            OperationKind::Install => Action::Install,
            OperationKind::Uninstall { purge_data: false } => Action::Remove,
            OperationKind::Uninstall { purge_data: true } => Action::Purge,
            OperationKind::Update => Action::Upgrade,
            _ => return Err(io::Error::other("the Root APT service does not change sources")),
        };
        let mut bytes = [0; 16];
        fs::File::open("/dev/urandom")?.read_exact(&mut bytes)?;
        let intent = Self {
            invocation_id: bytes.iter().map(|byte| format!("{byte:02x}")).collect(),
            action,
            packages: op.infos.iter().flat_map(|info| info.pkgnames.clone()).collect(),
            version,
            flatpak,
        };
        intent.canonical()
    }

    pub(crate) fn canonical(mut self) -> io::Result<Self> {
        if !valid_id(&self.invocation_id) {
            return Err(io::Error::other("Invalid package intent correlation"));
        }
        if matches!(self.action, Action::FlatpakInstall | Action::FlatpakUpdate) {
            if self.packages.is_empty() && self.version.is_none() && self.flatpak.as_ref().is_some_and(|target| {
                matches!(target.scope.as_str(), "user" | "system")
                    && !target.remote.is_empty() && target.remote.len() <= 128
                    && target.reference.starts_with("app/") && target.reference.len() <= 255
            }) {
                return Ok(self);
            }
            return Err(io::Error::other("Expected one Flatpak application and named source"));
        }
        if self.flatpak.is_some() || self.packages.is_empty()
            || self.packages.len() > HISTORY_LIMIT
            || self.packages.iter().any(|name| !crate::product::valid_package_name(name))
        {
            return Err(io::Error::other("a package intent requires an invocation and 1..128 exact Debian names"));
        }
        self.packages.sort();
        self.packages.dedup();
        if self.action == Action::InstallRelease {
            if self.packages.len() != 1 || !crate::product::claw_app_package(&self.packages[0])
                || !self.version.as_ref().is_some_and(|value| !value.is_empty()
                    && value.len() <= 128 && value.as_bytes()[0].is_ascii_digit()
                    && value.bytes().all(|byte| byte.is_ascii_alphanumeric() || b".+~-:".contains(&byte)))
            {
                return Err(io::Error::other("Expected one Claw App and its exact Debian release"));
            }
        } else if self.version.is_some() {
            return Err(io::Error::other("This package action does not accept a version"));
        }
        Ok(self)
    }

    pub fn operation(&self) -> Value {
        if let Some(target) = &self.flatpak {
            return json!({"action": "flatpak", "install": self.action == Action::FlatpakInstall, "target": target});
        }
        if let Some(version) = &self.version {
            return json!({"action": self.action, "package": self.packages[0], "version": version});
        }
        if self.packages.len() == 1 {
            json!({"action": self.action, "package": self.packages[0]})
        } else {
            json!({"action": format!("{}-packages", self.action.as_str()), "packages": self.packages})
        }
    }

    pub(crate) fn argv(&self, mode: Mode) -> Vec<String> {
        let mut args = vec![
            "__package_intent".into(), "--retained".into(), mode.as_str().into(),
            self.invocation_id.clone(), self.action.as_str().into(),
        ];
        if let Some(target) = &self.flatpak {
            args.extend([target.scope.clone(), target.remote.clone(), target.reference.clone()]);
        } else if let Some(version) = &self.version {
            args.push(format!("{}={version}", self.packages[0]));
        } else {
            args.extend(self.packages.iter().cloned());
        }
        args
    }

    fn save(&self) -> io::Result<()> {
        let directory = history_directory()?;
        fs::create_dir_all(&directory)?;
        if fs::read_dir(&directory)?.take(HISTORY_LIMIT).count() >= HISTORY_LIMIT {
            return Err(io::Error::other("Store's pending package handoff history is full; query Root completion/recovery for existing requests before submitting more"));
        }
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file = options.open(directory.join(format!("{}.json", self.invocation_id)))?;
        file.write_all(&serde_json::to_vec(self)?)?;
        file.sync_all()?;
        fs::File::open(directory)?.sync_all()
    }
}

#[derive(Clone, Debug)]
pub enum State {
    PermissionRequired(Vec<String>),
    PermissionReady,
    Accepted(String),
    Transaction(Value),
    RecoveryRequested(Value),
    Unconfirmed(String),
}

#[derive(Clone, Debug)]
pub struct Tracked {
    pub intent: Intent,
    pub state: State,
}

impl Tracked {
    pub fn confirmed_applied(&self) -> bool {
        matches!(&self.state, State::Transaction(record)
            if record["phase"] == "applied"
                && record["completion"]["confirmed"] == true
                && record["completion"]["status"] == "applied")
    }

    pub fn terminal(&self) -> bool {
        self.confirmed_applied()
            || matches!(&self.state, State::Transaction(record) if record["phase"] == "not_applied")
    }

    pub fn message(&self) -> String {
        let evidence = match &self.state {
            State::PermissionRequired(ids) => format!(
                "Critical sys.package permission is awaiting protected OS review: {}. \
                 Open OS Approvals (cos agent serve --open) or cos review show <id> outside \
                 Store, then continue this exact request. No package acceptance or effect is confirmed.",
                ids.join(", ")
            ),
            State::PermissionReady => "OS permission decisions are available for this intent. \
                Continue asks Root to revalidate and consume the complete exact decision set; \
                this status is not authority, acceptance or package success.".into(),
            State::Accepted(id) => format!(
                "Handed off to Root, request {id}. Accepted is not installed, removed or successful. \
                 Root may stop this Store window. Inspect cos package-transactions {id} outside Store."
            ),
            State::Transaction(record) => {
                let phase = record["phase"].as_str().unwrap_or("unknown");
                let outcome = if self.confirmed_applied() {
                    "Root confirms this exact transaction applied."
                } else if record["phase"] == "not_applied" {
                    "Root confirms this request was not applied."
                } else {
                    "Package success is not confirmed."
                };
                let mut text = format!("Root phase: {phase}. {outcome}");
                if let Some(review) = record["global_stop_review_id"].as_str() {
                    text.push_str(&format!(
                        " Separate protected global-impact review: {review}. Review the exact plan, \
                         affected Apps and unsaved-work warning in OS Approvals; package permission \
                         does not approve stopping all Apps."
                    ));
                }
                if let Some(reviews) = record["app_reviews"].as_array() {
                    for review in reviews {
                        if let Some(id) = review["review_id"].as_str() {
                            text.push_str(&format!(" Separate App delivery review: {id}."));
                        }
                    }
                }
                if let Some(error) = record["error"].as_str() {
                    text.push_str(&format!(" Root reports: {error}"));
                }
                text
            }
            State::RecoveryRequested(record) => format!(
                "Root retained a read-only reconciliation request for {}. Reconciliation has not \
                 completed; check OS status again. Last observed phase: {}. No APT replay was requested.",
                record["request_id"].as_str().unwrap_or("unknown"),
                record["phase"].as_str().unwrap_or("unknown"),
            ),
            State::Unconfirmed(error) => format!(
                "Package acceptance/completion is unconfirmed: {error}. \
                 Query Root before any new submission; do not replay effects. \
                 The OS must provide retained package-intent support; no direct provider fallback is available."
            ),
        };
        let target = match (&self.intent.flatpak, &self.intent.version) {
            (Some(target), _) => format!("{}: {} / {}", target.scope, target.remote, target.reference),
            (_, Some(version)) => format!("{}={version}", self.intent.packages[0]),
            _ => self.intent.packages.join(", "),
        };
        format!(
            "{}: {}\n{evidence}\nCorrelation: {}. Outside Store: cos package-transactions --invocation {}. \
             Recovery only reconciles evidence; it never reruns APT.",
            self.intent.action.as_str(), target,
            self.intent.invocation_id, self.intent.invocation_id,
        )
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Reply {
    version: u8,
    invocation_id: String,
    status: String,
    #[serde(default)]
    approval_requests: Vec<String>,
    #[serde(default)]
    receipt: Option<Value>,
    #[serde(default)]
    transaction: Option<Value>,
    #[serde(default)]
    reason: Option<String>,
}

fn valid_id(id: &str) -> bool {
    id.len() == 32 && id.bytes().all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

pub(crate) fn decode(intent: &Intent, value: Value) -> io::Result<State> {
    let reply: Reply = serde_json::from_value(value)?;
    if reply.version != 1 || reply.invocation_id != intent.invocation_id {
        return Err(io::Error::other("Root package intent protocol/correlation mismatch"));
    }
    match reply.status.as_str() {
        "permission_ready" if reply.receipt.is_none() && reply.transaction.is_none()
            && reply.approval_requests.is_empty() && reply.reason.is_none() =>
        {
            Ok(State::PermissionReady)
        }
        "permission_required" if reply.receipt.is_none() && reply.transaction.is_none() && reply.reason.is_none()
            && !reply.approval_requests.is_empty() && reply.approval_requests.len() <= HISTORY_LIMIT
            && reply.approval_requests.iter().all(|id| !id.is_empty() && id.len() <= 128
                && id.bytes().all(|byte| byte.is_ascii_alphanumeric() || b"-_".contains(&byte))) =>
        {
            Ok(State::PermissionRequired(reply.approval_requests))
        }
        "accepted" if reply.transaction.is_none() && reply.approval_requests.is_empty() && reply.reason.is_none() => {
            let receipt = reply.receipt.ok_or_else(|| io::Error::other("Root receipt is missing"))?;
            let id = receipt["request_id"].as_str().unwrap_or_default();
            if receipt["accepted"] != true || receipt["status"] != "accepted"
                || receipt["completion"] != "query_required"
                || receipt["invocation_id"] != intent.invocation_id || !valid_id(id)
            {
                return Err(io::Error::other("Root retained acceptance was not confirmed"));
            }
            Ok(State::Accepted(id.to_string()))
        }
        "transaction" | "recovery_requested" if reply.receipt.is_none()
            && reply.approval_requests.is_empty() && reply.reason.is_none() => {
            let record = reply.transaction.ok_or_else(|| io::Error::other("Root transaction is missing"))?;
            if !valid_id(record["request_id"].as_str().unwrap_or_default())
                || record["invocation_id"] != intent.invocation_id
                || record["operation"] != intent.operation()
                || !matches!(record["phase"].as_str(), Some(
                    "accepted" | "planning" | "awaiting_app_confirmation" | "awaiting_impact_confirmation"
                    | "retiring" | "cleanup_pending" | "dispatching" | "applied" | "not_applied" | "indeterminate"
                ))
            {
                return Err(io::Error::other("Root transaction does not match the exact package intent"));
            }
            Ok(if reply.status == "recovery_requested" {
                State::RecoveryRequested(record)
            } else { State::Transaction(record) })
        }
        "unconfirmed" if reply.receipt.is_none() && reply.transaction.is_none()
            && reply.approval_requests.is_empty() =>
        {
            Ok(State::Unconfirmed(reply.reason.unwrap_or_else(|| "Root outcome is unavailable".into())))
        }
        _ => Err(io::Error::other("Root did not provide recognized package evidence")),
    }
}

pub fn submit(op: &Operation) -> io::Result<Tracked> {
    crate::claw_glue::human_ui().map_err(io::Error::other)?;
    let intent = Intent::for_operation(op)?;
    // Persist only correlation/intent, never authority or a cached success.
    intent.save()?;
    Ok(refresh(&intent, Mode::Review))
}

pub fn refresh(intent: &Intent, mode: Mode) -> Tracked {
    let state = (|| {
        crate::claw_glue::human_ui().map_err(io::Error::other)?;
        if intent.clone().canonical()? != *intent {
            return Err(io::Error::other("package intent is not canonical"));
        }
        let value = claw_os_sdk::cos_call_json_with_binary(
            "/usr/local/bin/cos", "package", "intent", intent.argv(mode),
        ).map_err(io::Error::other)?;
        decode(intent, value)
    })().unwrap_or_else(|error| State::Unconfirmed(error.to_string()));
    let tracked = Tracked { intent: intent.clone(), state };
    if tracked.terminal() {
        // Only a fresh Root terminal projection can trim pending bookkeeping.
        // Cached intent files themselves never supply completion evidence.
        if let Ok(directory) = history_directory() {
            if let Err(error) = fs::remove_file(directory.join(format!("{}.json", intent.invocation_id))) {
                if error.kind() != io::ErrorKind::NotFound {
                    log::warn!("could not trim reconciled package correlation: {error}");
                }
            }
        }
    }
    tracked
}

fn history_directory() -> io::Result<PathBuf> {
    let root = std::env::var_os("COS_DATA_DIR").map(PathBuf::from)
        .filter(|root| root.is_absolute())
        .ok_or_else(|| io::Error::other("authenticated App data is unavailable; package intent was not dispatched"))?;
    Ok(root.join("package-handoffs"))
}

pub fn history() -> io::Result<Vec<Tracked>> {
    let directory = history_directory()?;
    let entries = match fs::read_dir(directory) {
        Ok(entries) => entries,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(error),
    };
    let mut result = Vec::new();
    for entry in entries.take(HISTORY_LIMIT + 1) {
        let entry = entry?;
        if result.len() >= HISTORY_LIMIT || !entry.file_type()?.is_file()
            || entry.metadata()?.len() > INTENT_BYTES
        {
            return Err(io::Error::other("package correlation history is invalid or too large"));
        }
        let intent: Intent = serde_json::from_reader(fs::File::open(entry.path())?)?;
        if intent.clone().canonical()? != intent
            || entry.file_name().as_os_str() != std::ffi::OsStr::new(&format!("{}.json", intent.invocation_id))
        {
            return Err(io::Error::other("package correlation history is not canonical"));
        }
        result.push(Tracked {
            intent,
            state: State::Unconfirmed("cached intent is not Root completion evidence".into()),
        });
    }
    Ok(result)
}

