// SPDX-License-Identifier: GPL-3.0-only
//! A private presentation cache of the OS owner's preferences, never an owner mount.

use cosmic::cosmic_config as local;
pub use local::{ConfigGet, ConfigSet, CosmicConfigEntry, Error};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock};

static FAILURE: OnceLock<Mutex<Option<String>>> = OnceLock::new();
static CANDIDATE: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

pub fn failure() -> Option<String> {
    FAILURE
        .get_or_init(|| Mutex::new(None))
        .lock()
        .unwrap()
        .clone()
        .or_else(cosmic_settings_provider_client::failure)
}

pub fn user_keyboard_layouts() -> Result<xkb_data::KeyboardLayouts, Error> {
    let entries = call("keyboard-catalog", "read", &[])?;
    let parent = std::env::var_os("COS_DATA_DIR")
        .map(PathBuf::from)
        .ok_or_else(|| {
            failed("owner keyboard catalog requires the authenticated App data binding")
        })?
        .join(".cache")
        .join("owner-preferences");
    std::fs::create_dir_all(&parent)?;
    let path = parent.join(format!(
        "catalog-{}-{}",
        std::process::id(),
        CANDIDATE.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
    ));
    std::fs::create_dir(&path)?;
    let _cache = Cache(path.clone());
    let mut layouts = Vec::new();
    for entry in entries {
        if !matches!(entry.key.as_str(), "xdg" | "legacy") {
            return Err(failed("invalid owner keyboard catalog source"));
        }
        let xml = path.join("catalog.xml");
        std::fs::write(&xml, entry.value)?;
        let catalog = xkb_data::get_keyboard_layouts(
            xml.to_str()
                .ok_or_else(|| failed("private keyboard catalog path is not UTF-8"))?,
        )?;
        layouts.extend(catalog.layout_list.layout);
    }
    Ok(xkb_data::KeyboardLayouts {
        layout_list: xkb_data::LayoutList { layout: layouts },
    })
}

fn failed(error: impl std::fmt::Display) -> Error {
    let message = error.to_string();
    *FAILURE.get_or_init(|| Mutex::new(None)).lock().unwrap() = Some(message.clone());
    Error::Io(std::io::Error::other(message))
}

fn canonical_id(id: &str) -> &str {
    // Retained shared types keep upstream IDs; the installed OS owns these namespaces.
    match id {
        id if id == cosmic_settings_config::shortcuts::ID => "com.yuos.Settings.Shortcuts",
        id if id == cosmic_settings_config::window_rules::ID => "com.yuos.Settings.WindowRules",
        id if id == cosmic_bg_config::NAME => "com.yuos.Background",
        id if id == cosmic_settings_daemon_config::NAME => "com.yuos.SettingsDaemon",
        "com.system76.CosmicPanel" => "com.yuos.Panel",
        "com.system76.CosmicPanel.Panel" => "com.yuos.Panel.Panel",
        "com.system76.CosmicPanel.Dock" => "com.yuos.Panel.Dock",
        _ => id,
    }
}

fn namespace(id: &str) -> Option<&'static str> {
    let id = canonical_id(id);
    Some(match id {
        "com.yuos.Comp" => "compositor",
        "com.yuos.Workspaces" => "workspaces",
        "com.yuos.Tk" => "toolkit",
        "com.yuos.Theme.Mode" => "theme-mode",
        "com.yuos.Theme.Light" => "theme-light",
        "com.yuos.Theme.Dark" => "theme-dark",
        "com.yuos.Theme.Light.Builder" => "theme-builder-light",
        "com.yuos.Theme.Dark.Builder" => "theme-builder-dark",
        "com.yuos.Panel.Panel" => "panel",
        "com.yuos.Panel.Dock" => "dock",
        "com.yuos.Panel" => "panel-container",
        "com.yuos.Idle" => "idle",
        "com.yuos.Audio" => "audio",
        "com.yuos.SettingsDaemon" => "daemon",
        "com.yuos.AppletTime" => "time",
        "com.yuos.Settings.Shortcuts" => "shortcuts",
        "com.yuos.Settings.WindowRules" => "window-rules",
        "com.yuos.Background" => "background",
        "com.yuos.Settings" => "regional",
        _ => return None,
    })
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Entry {
    key: String,
    value: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Snapshot {
    action: String,
    namespace: String,
    version: u8,
    #[serde(default)]
    status: Option<String>,
    entries: Vec<Entry>,
}

fn call(namespace: &str, action: &str, entries: &[Entry]) -> Result<Vec<Entry>, Error> {
    let mut request = json!({"namespace":namespace,"version":1,"action":action});
    if action == "write" {
        request["entries"] = serde_json::to_value(entries).map_err(failed)?;
    }
    let input = serde_json::to_vec(&request).map_err(failed)?;
    let response = std::thread::Builder::new()
        .name("owner-preferences-wire".into())
        .spawn(move || {
            let runtime = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .map_err(|error| error.to_string())?;
            runtime
                .block_on(claw_os_sdk::cos_call_json_async_with_stdin_binary(
                    "/usr/local/bin/yu",
                    "desktop-preferences",
                    "control",
                    ["__desktop-preferences", "--request-stdin"],
                    &input,
                ))
                .map_err(|error| error.to_string())
        })
        .map_err(failed)?
        .join()
        .map_err(|_| failed("OS preference transport stopped; the outcome is unconfirmed"))?
        .map_err(failed)?;
    decode(namespace, action, entries, response)
}

fn decode(
    namespace: &str,
    action: &str,
    requested: &[Entry],
    value: Value,
) -> Result<Vec<Entry>, Error> {
    if value.to_string().len() > 256 * 1024 {
        return Err(failed("OS preference snapshot exceeded its bound"));
    }
    let snapshot: Snapshot = serde_json::from_value(value).map_err(failed)?;
    if snapshot.namespace != namespace
        || snapshot.action != action
        || snapshot.version != 1
        || snapshot.entries.len() > 128
        || (action == "write"
            && (snapshot.status.as_deref() != Some("applied") || snapshot.entries != requested))
        || (action == "read" && snapshot.status.is_some())
    {
        return Err(failed(
            "OS did not confirm the requested desktop preferences",
        ));
    }
    let mut keys = std::collections::BTreeSet::new();
    for entry in &snapshot.entries {
        if !valid_key(&entry.key)
            || !keys.insert(&entry.key)
            || entry.value.len() > 64 * 1024
            || entry.value.contains('\0')
        {
            return Err(failed("invalid OS desktop preference entry"));
        }
    }
    Ok(snapshot.entries)
}

fn valid_key(key: &str) -> bool {
    !key.is_empty()
        && key.len() <= 64
        && key
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.'))
        && !key.starts_with('.')
}

#[derive(Clone, Debug)]
pub struct Config {
    local: local::Config,
    namespace: Option<&'static str>,
    path: Option<PathBuf>,
    id: String,
    ready: bool,
    _cache: Option<Arc<Cache>>,
}

#[derive(Debug)]
struct Cache(PathBuf);

impl Drop for Cache {
    fn drop(&mut self) {
        if let Err(error) = std::fs::remove_dir_all(&self.0) {
            tracing::warn!(%error, "could not retire private owner-preference cache");
        }
    }
}

impl std::ops::Deref for Config {
    type Target = local::Config;

    fn deref(&self) -> &Self::Target {
        &self.local
    }
}

impl Config {
    pub fn new(id: &str, version: u64) -> Result<Self, Error> {
        let id = canonical_id(id);
        let namespace = namespace(id).ok_or_else(|| Error::InvalidName(id.into()))?;
        if version != 1 {
            return Err(Error::InvalidName(format!("{id}/v{version}")));
        }
        let Some(data) = std::env::var_os("COS_DATA_DIR").map(PathBuf::from) else {
            let _ = failed("owner preferences require the authenticated App data binding");
            return Ok(Self {
                local: local::Config::system(id, version)?,
                namespace: Some(namespace),
                path: None,
                id: id.into(),
                ready: false,
                _cache: None,
            });
        };
        let parent = data.join(".cache").join("owner-preferences");
        std::fs::create_dir_all(&parent)?;
        let base = parent.join(format!(
            "{namespace}-{}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map_err(failed)?
                .as_nanos(),
            CANDIDATE.fetch_add(1, std::sync::atomic::Ordering::Relaxed),
        ));
        std::fs::create_dir(&base)?;
        let cache = Arc::new(Cache(base.clone()));
        let path = base.join("cosmic").join(id).join("v1");
        let local = local::Config::with_custom_path(id, version, base)?;
        let mut config = Self {
            local,
            namespace: Some(namespace),
            path: Some(path),
            id: id.into(),
            ready: false,
            _cache: Some(cache),
        };
        let _ = config.refresh();
        Ok(config)
    }

    pub fn system(id: &str, version: u64) -> Result<Self, Error> {
        let id = canonical_id(id);
        Ok(Self {
            local: local::Config::system(id, version)?,
            namespace: None,
            path: None,
            id: id.into(),
            ready: true,
            _cache: None,
        })
    }

    pub fn new_state(id: &str, version: u64) -> Result<Self, Error> {
        let id = canonical_id(id);
        if id != "com.yuos.Background" {
            return Err(Error::InvalidName(id.into()));
        }
        let mut config = Self::new(id, version)?;
        config.namespace = Some("background-state");
        let _ = config.refresh();
        Ok(config)
    }

    pub fn refresh(&mut self) -> Result<(), Error> {
        self.ready = false;
        let Some(namespace) = self.namespace else {
            return Ok(());
        };
        let Some(path) = self.path.as_ref() else {
            return Err(failed("owner preference cache is unavailable"));
        };
        // A denied refresh must not reuse a previous session's owner snapshot.
        for entry in std::fs::read_dir(path)? {
            let entry = entry?;
            if entry.file_type()?.is_file() {
                std::fs::remove_file(entry.path())?;
            }
        }
        install_defaults(&self.id, path)?;
        let entries = call(namespace, "read", &[])?;
        install(path, &entries)?;
        self.ready = true;
        Ok(())
    }

    pub fn entry<T: CosmicConfigEntry>(&self) -> Result<T, Error> {
        if !self.ready {
            return Err(failed(
                "owner preference snapshot was not authorized or available",
            ));
        }
        read_entry(&self.local)
    }

    fn write(&self, entries: &[Entry]) -> Result<(), Error> {
        let namespace = self
            .namespace
            .ok_or_else(|| failed("system defaults are read-only"))?;
        call(namespace, "write", entries)?;
        if let Some(path) = &self.path {
            install(path, entries).map_err(|error| {
                failed(format!(
                    "OS saved the preferences but the presentation cache failed: {error}; refresh before retrying"
                ))
            })?;
        }
        Ok(())
    }

    pub fn transaction(&self) -> Transaction<'_> {
        Transaction {
            config: self,
            entries: Mutex::new(Vec::new()),
        }
    }

    pub fn write_entry<T: CosmicConfigEntry>(&self, entry: &T) -> Result<(), Error> {
        self.edit_raw(&mut (), |_, config| entry.write_entry(config))
    }

    pub fn edit<T: Clone + CosmicConfigEntry, R>(
        &self,
        value: &mut T,
        change: impl FnOnce(&mut T, &local::Config) -> Result<R, Error>,
    ) -> Result<R, Error> {
        self.edit_raw(value, |next, local| {
            *next = read_entry(local)?;
            change(next, local)
        })
    }

    pub fn edit_raw<T: Clone, R>(
        &self,
        value: &mut T,
        change: impl FnOnce(&mut T, &local::Config) -> Result<R, Error>,
    ) -> Result<R, Error> {
        let path = self
            .path
            .as_ref()
            .ok_or_else(|| failed("no App preference cache"))?;
        let namespace = self
            .namespace
            .ok_or_else(|| failed("system defaults are read-only"))?;
        let current = call(namespace, "read", &[])?;
        for entry in std::fs::read_dir(path)? {
            let entry = entry?;
            if entry.file_type()?.is_file() {
                std::fs::remove_file(entry.path())?;
            }
        }
        install_defaults(&self.id, path)?;
        install(path, &current)?;
        let candidate = path.join(format!(
            ".candidate-{}-{}",
            std::process::id(),
            CANDIDATE.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
        ));
        let result = (|| {
            let config = local::Config::with_custom_path(&self.id, 1, candidate.clone())?;
            let directory = candidate.join("cosmic").join(&self.id).join("v1");
            for entry in std::fs::read_dir(path)? {
                let entry = entry?;
                if entry.file_type()?.is_file() {
                    std::fs::copy(entry.path(), directory.join(entry.file_name()))?;
                }
            }
            let mut next = value.clone();
            let result = change(&mut next, &config)?;
            let mut entries = Vec::new();
            for entry in std::fs::read_dir(directory)? {
                let entry = entry?;
                let key = entry.file_name().to_string_lossy().into_owned();
                if !valid_key(&key) || !entry.file_type()?.is_file() {
                    return Err(failed("invalid private preference candidate"));
                }
                let body = std::fs::read_to_string(entry.path())?;
                if std::fs::read_to_string(path.join(&key)).ok().as_deref() != Some(&body) {
                    entries.push(Entry { key, value: body });
                }
            }
            entries.sort_by(|left, right| left.key.cmp(&right.key));
            if !entries.is_empty() {
                self.write(&entries)?;
            }
            *value = next;
            Ok(result)
        })();
        if candidate.exists() {
            std::fs::remove_dir_all(candidate)?;
        }
        result
    }
}

fn read_entry<T: CosmicConfigEntry>(config: &local::Config) -> Result<T, Error> {
    match T::get_entry(config) {
        Ok(value) => Ok(value),
        Err((errors, value)) => {
            if errors.iter().all(|error| matches!(error, Error::NotFound | Error::NoConfigDirectory)
                || matches!(error, Error::GetKey(_, cause) if cause.kind() == std::io::ErrorKind::NotFound))
            {
                Ok(value)
            } else {
                Err(failed(errors.iter().map(ToString::to_string).collect::<Vec<_>>().join("; ")))
            }
        }
    }
}

pub fn theme() -> Result<cosmic::Theme, Error> {
    let mode = Config::new(cosmic::cosmic_theme::THEME_MODE_ID, 1)?
        .entry::<cosmic::cosmic_theme::ThemeMode>()?;
    let id = if mode.is_dark {
        cosmic::cosmic_theme::DARK_THEME_ID
    } else {
        cosmic::cosmic_theme::LIGHT_THEME_ID
    };
    let theme = Config::new(id, 1)?.entry::<cosmic::cosmic_theme::Theme>()?;
    Ok(cosmic::Theme {
        theme_type: cosmic::theme::ThemeType::Custom(Arc::new(theme)),
        ..cosmic::Theme::default()
    })
}
pub fn watch<T>(id: &'static str) -> cosmic::iced::Subscription<local::Update<T>>
where
    T: 'static + Send + Sync + PartialEq + Clone + CosmicConfigEntry,
{
    watch_internal::<T>(id, false)
}

pub fn watch_state<T>(id: &'static str) -> cosmic::iced::Subscription<local::Update<T>>
where
    T: 'static + Send + Sync + PartialEq + Clone + CosmicConfigEntry,
{
    watch_internal::<T>(id, true)
}

fn watch_internal<T>(id: &'static str, state: bool) -> cosmic::iced::Subscription<local::Update<T>>
where
    T: 'static + Send + Sync + PartialEq + Clone + CosmicConfigEntry,
{
    cosmic::iced::Subscription::run_with((id, state), |(id, state)| {
        let id = *id;
        let state = *state;
        cosmic::iced::stream::channel(
            4,
            move |mut output: futures::channel::mpsc::Sender<local::Update<T>>| async move {
                use futures::SinkExt;
                let mut previous = None;
                loop {
                    let result = tokio::task::spawn_blocking(move || {
                        (if state {
                            Config::new_state(id, T::VERSION)
                        } else {
                            Config::new(id, T::VERSION)
                        })
                        .map(|config| T::get_entry(&config))
                    })
                    .await;
                    let (errors, value) = match result {
                        Ok(Ok(Ok(value))) => (Vec::new(), value),
                        Ok(Ok(Err((errors, value)))) => (errors, value),
                        Ok(Err(error)) => {
                            let _ = failed(error);
                            tokio::time::sleep(std::time::Duration::from_secs(2)).await;
                            continue;
                        }
                        Err(error) => {
                            let _ = failed(error);
                            return;
                        }
                    };
                    if previous.as_ref() != Some(&value) {
                        previous = Some(value.clone());
                        if output
                            .send(local::Update {
                                errors,
                                keys: Vec::new(),
                                config: value,
                            })
                            .await
                            .is_err()
                        {
                            return;
                        }
                    }
                    tokio::time::sleep(std::time::Duration::from_secs(2)).await;
                }
            },
        )
    })
}
impl ConfigGet for Config {
    fn get<T: serde::de::DeserializeOwned>(&self, key: &str) -> Result<T, Error> {
        if let Some(namespace) = self.namespace {
            let entries = call(namespace, "read", &[])?;
            return match entries.into_iter().find(|entry| entry.key == key) {
                Some(entry) => ron::from_str(&entry.value).map_err(Error::from),
                None => self.get_system_default(key),
            };
        }
        self.local.get(key)
    }

    fn get_local<T: serde::de::DeserializeOwned>(&self, key: &str) -> Result<T, Error> {
        if let Some(namespace) = self.namespace {
            return call(namespace, "read", &[])?
                .into_iter()
                .find(|entry| entry.key == key)
                .map_or(Err(Error::NotFound), |entry| {
                    ron::from_str(&entry.value).map_err(Error::from)
                });
        }
        self.local.get_local(key)
    }

    fn get_system_default<T: serde::de::DeserializeOwned>(&self, key: &str) -> Result<T, Error> {
        local::Config::system(&self.id, 1)?.get_system_default(key)
    }
}

impl ConfigSet for Config {
    fn set<T: Serialize>(&self, key: &str, value: T) -> Result<(), Error> {
        if !valid_key(key) {
            return Err(Error::InvalidName(key.into()));
        }
        self.write(&[Entry {
            key: key.into(),
            value: ron::ser::to_string_pretty(&value, ron::ser::PrettyConfig::new())?,
        }])
    }
}

pub struct Transaction<'a> {
    config: &'a Config,
    entries: Mutex<Vec<Entry>>,
}

impl ConfigSet for Transaction<'_> {
    fn set<T: Serialize>(&self, key: &str, value: T) -> Result<(), Error> {
        if !valid_key(key) {
            return Err(Error::InvalidName(key.into()));
        }
        self.entries.lock().unwrap().push(Entry {
            key: key.into(),
            value: ron::ser::to_string_pretty(&value, ron::ser::PrettyConfig::new())?,
        });
        Ok(())
    }
}

impl Transaction<'_> {
    pub fn commit(self) -> Result<(), Error> {
        let entries = self.entries.into_inner().unwrap();
        if entries.is_empty() {
            return Ok(());
        }
        self.config.write(&entries)
    }
}

pub fn set_field<T: Serialize + PartialEq>(
    config: &Config,
    key: &str,
    current: &mut T,
    next: T,
) -> Result<bool, Error> {
    if *current == next {
        return Ok(false);
    }
    config.set(key, &next)?;
    *current = next;
    Ok(true)
}

#[cfg(feature = "wayland")]
pub fn panel(name: &str) -> Result<Config, Error> {
    Config::new(&format!("com.yuos.Panel.{name}"), 1)
}

#[cfg(feature = "wayland")]
pub fn panels() -> Result<cosmic_panel_config::CosmicPanelContainerConfig, Error> {
    let names = Config::new("com.yuos.Panel", 1)?.get::<Vec<String>>("entries")?;
    let mut config_list = Vec::new();
    for name in names {
        let helper = panel(&name)?;
        config_list.push(
            cosmic_panel_config::CosmicPanelConfig::get_entry(&helper)
                .unwrap_or_else(|(_, value)| value),
        );
    }
    Ok(cosmic_panel_config::CosmicPanelContainerConfig { config_list })
}

#[cfg(feature = "wayland")]
pub fn write_panels(config: &cosmic_panel_config::CosmicPanelContainerConfig) -> Result<(), Error> {
    for entry in &config.config_list {
        panel(&entry.name)?.write_entry(entry)?;
    }
    Config::new("com.yuos.Panel", 1)?.set(
        "entries",
        config
            .config_list
            .iter()
            .map(|entry| entry.name.as_str())
            .collect::<Vec<_>>(),
    )
}

fn install(path: &Path, entries: &[Entry]) -> Result<(), Error> {
    for entry in entries {
        if !valid_key(&entry.key) {
            return Err(Error::InvalidName(entry.key.clone()));
        }
        std::fs::write(path.join(&entry.key), &entry.value)?;
    }
    Ok(())
}

fn install_defaults(id: &str, destination: &Path) -> Result<(), Error> {
    let roots =
        std::env::var_os("XDG_DATA_DIRS").unwrap_or_else(|| "/usr/local/share:/usr/share".into());
    for root in std::env::split_paths(&roots)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
    {
        let path = root.join("cosmic").join(id).join("v1");
        let entries = match std::fs::read_dir(path) {
            Ok(entries) => entries,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
            Err(error) => return Err(error.into()),
        };
        for entry in entries {
            let entry = entry?;
            let key = entry.file_name().to_string_lossy().into_owned();
            if valid_key(&key) && entry.file_type()?.is_file() {
                std::fs::copy(entry.path(), destination.join(key))?;
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/unit/owner_config.rs"
    ));
}
