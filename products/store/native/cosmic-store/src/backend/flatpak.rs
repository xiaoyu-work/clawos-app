use std::{error::Error, sync::Arc};

use base64::{Engine, engine::general_purpose::STANDARD};
use cosmic::widget;
use serde::Deserialize;
use serde_json::json;

use super::{Backend, Package};
use crate::{AppId, AppInfo, AppstreamCache, Operation, product};

#[derive(Deserialize)]
struct CatalogChunk {
    revision: String,
    source: Option<String>,
    offset: usize,
    size: usize,
    data: String,
    next: Option<String>,
}

#[derive(Deserialize)]
struct Inventory {
    apps: Vec<Installed>,
}

#[derive(Deserialize)]
struct Installed {
    id: String,
    #[serde(rename = "ref")]
    reference: String,
    remote: String,
    installed: String,
    candidate: Option<String>,
}

#[derive(Debug)]
pub struct Flatpak {
    user: bool,
    locale: String,
    appstream_caches: Vec<AppstreamCache>,
}

impl Flatpak {
    pub fn new(user: bool, locale: &str) -> Self {
        Self {
            user,
            locale: locale.into(),
            appstream_caches: Vec::new(),
        }
    }

    fn scope(&self) -> &'static str {
        if self.user { "user" } else { "system" }
    }

    fn source_id(&self, remote: &str) -> String {
        if self.user {
            remote.into()
        } else {
            format!("{remote} (system)")
        }
    }

    fn packages(&self, action: &str) -> Result<Vec<Package>, Box<dyn Error>> {
        let inventory: Inventory =
            serde_json::from_value(product::query(action, json!({"scope": self.scope()}))?)?;
        Ok(inventory
            .apps
            .into_iter()
            .map(|item| {
                let id = AppId::new(&item.id);
                let source = self.source_id(&item.remote);
                let metadata = self
                    .appstream_caches
                    .iter()
                    .find(|cache| cache.source_id == source)
                    .and_then(|cache| cache.infos.get(&id).map(|info| (cache, info)));
                let (mut info, icon) = match metadata {
                    Some((cache, info)) => ((**info).clone(), cache.icon(info)),
                    None => (
                        AppInfo {
                            source_id: source.clone(),
                            source_name: source,
                            name: item.id,
                            ..AppInfo::default()
                        },
                        widget::icon::from_name("package-x-generic")
                            .size(128)
                            .handle(),
                    ),
                };
                info.flatpak_refs = vec![item.reference];
                let mut extra = std::collections::HashMap::new();
                let version = match item.candidate {
                    Some(candidate) => {
                        extra.insert("previous_version".into(), item.installed);
                        candidate
                    }
                    None => item.installed,
                };
                Package {
                    id,
                    icon,
                    info: Arc::new(info),
                    version,
                    extra,
                }
            })
            .collect())
    }
}

impl Backend for Flatpak {
    fn load_caches(&mut self, _refresh: bool) -> Result<(), Box<dyn Error>> {
        let invalid = || "The Flatpak catalog changed or returned an incomplete snapshot";
        let mut caches = Vec::new();
        let mut cursor: Option<String> = None;
        let mut revision = None;
        let mut current: Option<(String, usize, Vec<u8>)> = None;
        let mut received = 0;
        loop {
            let chunk: CatalogChunk = serde_json::from_value(product::query(
                "flatpak-catalog",
                json!({"scope": self.scope(), "cursor": cursor}),
            )?)?;
            let Some(remote) = chunk.source else {
                if cursor.is_some() || chunk.next.is_some() {
                    return Err(invalid().into());
                }
                break;
            };
            if revision
                .as_ref()
                .is_some_and(|prior| prior != &chunk.revision)
                || chunk.size == 0
                || chunk.size > 128 * 1024 * 1024
            {
                return Err(invalid().into());
            }
            revision = Some(chunk.revision);
            let (expected, size, bytes) =
                current.get_or_insert_with(|| (remote.clone(), chunk.size, Vec::new()));
            let data = STANDARD.decode(chunk.data)?;
            received += data.len();
            if *expected != remote
                || *size != chunk.size
                || bytes.len() != chunk.offset
                || data.is_empty()
                || bytes.len() + data.len() > *size
                || received > 256 * 1024 * 1024
            {
                return Err(invalid().into());
            }
            bytes.extend_from_slice(&data);
            if bytes.len() == *size {
                let source = self.source_id(&remote);
                let mut cache = AppstreamCache::new(
                    source.clone(),
                    source,
                    Vec::new(),
                    Vec::new(),
                    &self.locale,
                );
                cache.extend_controlled_bytes(&remote, bytes)?;
                cache.infos.retain(|_, info| {
                    matches!(info.flatpak_refs.as_slice(), [reference] if reference.starts_with("app/"))
                });
                caches.push(cache);
                current = None;
            }
            cursor = chunk.next;
            if cursor.is_none() {
                if current.is_some() {
                    return Err(invalid().into());
                }
                break;
            }
        }
        self.appstream_caches = caches;
        Ok(())
    }

    fn info_caches(&self) -> &[AppstreamCache] {
        &self.appstream_caches
    }

    fn installed(&self) -> Result<Vec<Package>, Box<dyn Error>> {
        self.packages("flatpak-installed")
    }

    fn updates(&self) -> Result<Vec<Package>, Box<dyn Error>> {
        self.packages("flatpak-updates")
    }

    fn file_packages(&self, _path: &str) -> Result<Vec<Package>, Box<dyn Error>> {
        Err(crate::package::FLATPAK_UNAVAILABLE.into())
    }

    fn operation(
        &self,
        op: &Operation,
        _callback: Box<dyn FnMut(f32) + 'static>,
    ) -> Result<crate::package::Tracked, Box<dyn Error>> {
        Ok(crate::package::submit(op)?)
    }
}
