use cosmic::widget;
use serde::Deserialize;
use serde_json::json;
use std::{collections::HashMap, error::Error, fmt::Write, sync::Arc};

use super::{Backend, Package};
use crate::{AppId, AppInfo, AppstreamCache, GStreamerCodec, Operation, product};

#[derive(Deserialize)]
struct CatalogItem {
    source: String,
    xml: String,
}

#[derive(Deserialize)]
struct CatalogPage {
    revision: String,
    configured: bool,
    items: Vec<CatalogItem>,
    count: usize,
    total: usize,
    next: Option<String>,
}

#[derive(Deserialize)]
struct Installed {
    packages: Vec<String>,
    versions: HashMap<String, String>,
}

#[derive(Deserialize)]
struct Update {
    package: String,
    new_version: String,
    old_version: String,
}

#[derive(Deserialize)]
struct Updates {
    upgradable: Vec<Update>,
}

#[derive(Debug)]
pub struct Packagekit {
    appstream_caches: Vec<AppstreamCache>,
}

impl Packagekit {
    pub fn new(locale: &str) -> Result<Self, Box<dyn Error>> {
        Ok(Self {
            appstream_caches: vec![Self::cache(locale)],
        })
    }

    fn cache(locale: &str) -> AppstreamCache {
        AppstreamCache::new(
            "packagekit".into(),
            "System".into(),
            Vec::new(),
            Vec::new(),
            locale,
        )
    }

    fn packages(&self, rows: Vec<(String, String)>) -> Result<Vec<Package>, Box<dyn Error>> {
        let cache = &self.appstream_caches[0];
        let mut packages = Vec::new();
        let mut system_packages = Vec::new();
        for (name, version) in rows {
            if !product::valid_package_name(&name) {
                return Err("The OS package reader returned an invalid package name".into());
            }
            match cache.pkgnames.get(&name) {
                Some(ids) => {
                    for id in ids {
                        if let Some(info) = cache.infos.get(id) {
                            packages.push(Package {
                                id: id.clone(),
                                icon: cache.icon(info),
                                info: info.clone(),
                                version: version.clone(),
                                extra: HashMap::new(),
                            });
                        }
                    }
                }
                None => system_packages.push((name, version)),
            }
        }
        if !system_packages.is_empty() {
            let name = crate::fl!("system-packages");
            let summary = crate::fl!("system-packages-summary", count = system_packages.len());
            let mut description = String::new();
            let mut pkgnames = Vec::with_capacity(system_packages.len());
            let mut extra = HashMap::new();
            for (name, version) in system_packages {
                let _ = writeln!(description, " * {}: {}", name, version);
                extra.insert(format!("{}_update", name), version);
                pkgnames.push(name);
            }
            packages.push(Package {
                id: AppId::system(),
                icon: widget::icon::from_name("package-x-generic")
                    .size(128)
                    .handle(),
                info: Arc::new(AppInfo {
                    source_id: cache.source_id.clone(),
                    source_name: cache.source_name.clone(),
                    name,
                    summary,
                    description,
                    pkgnames,
                    ..Default::default()
                }),
                version: String::new(),
                extra,
            });
        }
        Ok(packages)
    }
}

impl Backend for Packagekit {
    fn load_caches(&mut self, _refresh: bool) -> Result<(), Box<dyn Error>> {
        let mut cache = Self::cache(&self.appstream_caches[0].locale);
        let mut cursor: Option<String> = None;
        let mut revision = None;
        let mut received = 0;
        loop {
            let page: CatalogPage =
                serde_json::from_value(product::query("catalog", json!({"cursor": cursor}))?)?;
            if !page.configured {
                return Err(
                    "OS_PACKAGE_CATALOG_UNAVAILABLE: no standard system catalog is configured"
                        .into(),
                );
            }
            if page.count != page.items.len()
                || page.total > 100_000
                || received + page.count > page.total
                || revision
                    .as_ref()
                    .is_some_and(|expected| expected != &page.revision)
                || page.items.is_empty() && page.next.is_some()
            {
                return Err("The OS catalog page does not match its retained revision".into());
            }
            revision = Some(page.revision);
            for item in page.items {
                cache.extend_controlled_xml(&item.source, &item.xml)?;
            }
            received += page.count;
            match page.next {
                Some(next) => cursor = Some(next),
                None => {
                    if received != page.total {
                        return Err("The OS catalog snapshot is incomplete".into());
                    }
                    break;
                }
            }
        }
        self.appstream_caches[0] = cache;
        Ok(())
    }

    fn info_caches(&self) -> &[AppstreamCache] {
        &self.appstream_caches
    }

    fn installed(&self) -> Result<Vec<Package>, Box<dyn Error>> {
        let installed: Installed = serde_json::from_value(product::query("installed", json!({}))?)?;
        let rows = installed
            .packages
            .into_iter()
            .map(|name| {
                let version = installed
                    .versions
                    .get(&name)
                    .ok_or("The OS package inventory omitted an installed version")?
                    .clone();
                Ok((name, version))
            })
            .collect::<Result<Vec<_>, Box<dyn Error>>>()?;
        self.packages(rows)
    }

    fn updates(&self) -> Result<Vec<Package>, Box<dyn Error>> {
        let updates: Updates = serde_json::from_value(product::query("updates", json!({}))?)?;
        let mut installed = HashMap::new();
        let mut rows = Vec::new();
        for update in updates.upgradable {
            installed.insert(update.package.clone(), update.old_version);
            rows.push((update.package, update.new_version));
        }
        let mut packages = self.packages(rows)?;
        for package in packages.iter_mut().filter(|package| package.id.is_system()) {
            for name in &package.info.pkgnames {
                if let Some(version) = installed.get(name) {
                    package
                        .extra
                        .insert(format!("{}_installed", name), version.clone());
                }
            }
        }
        Ok(packages)
    }

    fn file_packages(&self, _path: &str) -> Result<Vec<Package>, Box<dyn Error>> {
        Err(
            "OS_PACKAGE_PROVIDER_UNSUPPORTED: local Debian archive inspection is unavailable"
                .into(),
        )
    }

    fn gstreamer_packages(&self, _codec: &GStreamerCodec) -> Result<Vec<Package>, Box<dyn Error>> {
        Err(
            "OS_PACKAGE_PROVIDER_UNSUPPORTED: codec resolution requires a controlled OS provider"
                .into(),
        )
    }

    fn operation(
        &self,
        op: &Operation,
        _f: Box<dyn FnMut(f32) + 'static>,
    ) -> Result<crate::package::Tracked, Box<dyn Error>> {
        Ok(crate::package::submit(op)?)
    }
}
