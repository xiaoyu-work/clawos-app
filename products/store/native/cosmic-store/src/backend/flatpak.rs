use cosmic::widget;
use futures::StreamExt;
use libflatpak::{Installation, gio::Cancellable, glib, prelude::*};
use std::{
    collections::HashMap,
    error::Error,
    fmt::Write,
    sync::Arc,
};

use super::{Backend, Package};
use crate::{AppId, AppInfo, AppUrl, AppstreamCache, Operation};

#[derive(Debug)]
pub struct Flatpak {
    user: bool,
    appstream_caches: Vec<AppstreamCache>,
}

impl Flatpak {
    fn installation(&self) -> Result<Installation, glib::Error> {
        if self.user {
            Installation::new_user(Cancellable::NONE)
        } else {
            Installation::new_system(Cancellable::NONE)
        }
    }

    fn source_id(&self, remote_name: &str) -> String {
        if self.user {
            remote_name.to_string()
        } else {
            format!("{remote_name} (system)")
        }
    }

    pub fn new(user: bool, locale: &str) -> Result<Self, Box<dyn Error>> {
        let mut this = Self {
            user,
            appstream_caches: Vec::new(),
        };

        let inst = this.installation()?;
        for remote in inst.list_remotes(Cancellable::NONE)? {
            let source_id = match remote.name() {
                Some(name) => this.source_id(&name),
                None => {
                    log::warn!("remote {:?} missing name", remote);
                    continue;
                }
            };

            let appstream_dir = match remote.appstream_dir(None).and_then(|x| x.path()) {
                Some(some) => some,
                None => {
                    log::warn!("remote {:?} missing appstream dir", remote);
                    continue;
                }
            };

            let mut paths = Vec::new();
            let xml_gz_path = appstream_dir.join("appstream.xml.gz");
            if xml_gz_path.is_file() {
                paths.push(xml_gz_path);
            } else {
                let xml_path = appstream_dir.join("appstream.xml");
                if xml_path.is_file() {
                    paths.push(xml_path);
                }
            }

            let mut icons_paths = Vec::new();
            let icons_path = appstream_dir.join("icons");
            if icons_path.is_dir() {
                match icons_path.into_os_string().into_string() {
                    Ok(ok) => icons_paths.push(ok),
                    Err(os_string) => {
                        log::error!("failed to convert {:?} to string", os_string)
                    }
                }
            }

            let source_name = match remote.title() {
                Some(title) => this.source_id(&title),
                None => source_id.clone(),
            };
            this.appstream_caches.push(AppstreamCache::new(
                source_id,
                source_name,
                paths,
                icons_paths,
                locale,
            ));
        }

        // We don't store the installation because it is not Send
        Ok(this)
    }

    fn ref_to_package<R: InstalledRefExt + RefExt>(&self, r: &R) -> Option<Package> {
        let id_raw = r.name()?;
        let id = AppId::new(&id_raw);
        let origin = r.origin()?;
        for appstream_cache in self.appstream_caches.iter() {
            if appstream_cache.source_id != self.source_id(&origin) {
                // Only show items from correct cache
                continue;
            }

            //TODO: better matching of .desktop suffix
            let info = match appstream_cache.infos.get(&id) {
                Some(some) => some,
                None => continue,
            };

            let mut extra = HashMap::new();
            if let Some(arch) = r.arch() {
                extra.insert("arch".to_string(), arch.to_string());
            }
            if let Some(branch) = r.branch() {
                extra.insert("branch".to_string(), branch.to_string());
            }

            return Some(Package {
                id: id.clone(),
                icon: appstream_cache.icon(info),
                info: info.clone(),
                version: r.appdata_version().unwrap_or_default().to_string(),
                extra,
            });
        }

        log::debug!("failed to find info for {:?} from {}", id, origin);
        None
    }

    fn refs_to_packages<R: InstalledRefExt + RefExt>(&self, rs: Vec<R>) -> Vec<Package> {
        let mut packages = Vec::new();
        let mut system_packages = Vec::new();
        for r in rs {
            match self.ref_to_package(&r) {
                Some(package) => {
                    packages.push(package);
                }
                None => {
                    system_packages.push((
                        r.format_ref().unwrap_or_default().to_string(),
                        r.appdata_version()
                            .or(r.branch())
                            .unwrap_or_default()
                            .to_string(),
                    ));
                }
            }
        }

        if !system_packages.is_empty() {
            //TODO: use correct appstream cache, or do not bother to specify it
            let appstream_cache = &self.appstream_caches[0];
            let name = crate::fl!("flatpak-runtimes");
            let summary = crate::fl!("system-packages-summary", count = system_packages.len());
            let mut description = String::new();
            let mut flatpak_refs = Vec::with_capacity(system_packages.len());
            let mut extra = HashMap::new();
            for (flatpak_ref, version) in system_packages {
                let _ = writeln!(description, " * {}: {}", flatpak_ref, version);
                // Store version info for the release notes display
                extra.insert(format!("{}_installed", flatpak_ref), version);
                flatpak_refs.push(flatpak_ref);
            }
            //TODO: translate
            packages.push(Package {
                id: AppId::system(),
                icon: widget::icon::from_name("package-x-generic")
                    .size(128)
                    .handle(),
                //TODO: fill in more AppInfo fields
                info: Arc::new(AppInfo {
                    source_id: appstream_cache.source_id.clone(),
                    source_name: appstream_cache.source_name.clone(),
                    name,
                    summary,
                    description,
                    flatpak_refs,
                    ..Default::default()
                }),
                version: String::new(),
                extra,
            });
        }

        packages
    }
}

impl Backend for Flatpak {
    fn load_caches(&mut self, _refresh: bool) -> Result<(), Box<dyn Error>> {
        let appstream_caches = std::mem::take(&mut self.appstream_caches);
        let local_set = tokio::task::LocalSet::new();

        self.appstream_caches = futures::executor::block_on(async move {
            local_set.run_until(async move {
                // Parallel reload of appstream caches.
                appstream_caches
                    .into_iter()
                    .map(|mut cache| async move {
                        tokio::task::spawn_blocking(move || {
                            cache.reload();
                            cache
                        })
                        .await
                        .expect("flatpak worker thread failed to join")
                    })
                    .collect::<futures::stream::FuturesOrdered<_>>()
                    .collect::<Vec<AppstreamCache>>()
                    .await
            })
            .await
        });

        Ok(())
    }

    fn info_caches(&self) -> &[AppstreamCache] {
        &self.appstream_caches
    }

    fn installed(&self) -> Result<Vec<Package>, Box<dyn Error>> {
        let inst = self.installation()?;
        let packages = self.refs_to_packages(inst.list_installed_refs(Cancellable::NONE)?);
        Ok(packages)
    }

    fn updates(&self) -> Result<Vec<Package>, Box<dyn Error>> {
        let inst = self.installation()?;
        let packages =
            self.refs_to_packages(inst.list_installed_refs_for_update(Cancellable::NONE)?);
        Ok(packages)
    }

    fn file_packages(&self, path: &str) -> Result<Vec<Package>, Box<dyn Error>> {
        if !self.user {
            return Err(
                "flatpak backend only supports installing files with user installation"
                    .to_string()
                    .into(),
            );
        }

        if !path.ends_with(".flatpakref") {
            return Err(format!("flatpak backend does not support file {path:?}").into());
        }

        let path = crate::claw_glue::read_path(std::path::Path::new(path))
            .map_err(|error| -> Box<dyn Error> { crate::claw_glue::user_message(&error).into() })?;
        let path = path.to_str().ok_or("Flatpak ref path must be UTF-8")?;
        let entry = freedesktop_entry_parser::parse_entry(path)?;
        if !entry.has_section("Flatpak Ref") {
            return Err(format!("flatpak ref {path:?} missing Flatpak Ref section").into());
        }

        let get_attr = |key| entry.get("Flatpak Ref", key).and_then(|attr| attr.first());

        let id = get_attr("Name")
            .ok_or_else(|| format!("flatpak ref {path:?} missing Name attribute"))?;
        let url =
            get_attr("Url").ok_or_else(|| format!("flatpak ref {path:?} missing Url attribute"))?;

        let mut source_id = url.to_string();
        let mut source_name = url.to_string();
        let inst = self.installation()?;
        for remote in inst.list_remotes(Cancellable::NONE)? {
            if remote.url().is_some_and(|u| u == *url) {
                // Check if already installed
                if let Ok(r) = inst.current_installed_app(id, Cancellable::NONE) {
                    return Ok(self.refs_to_packages(vec![r]));
                }
                let Some(name) = remote.name() else {
                    log::warn!("remote {:?} missing name", remote);
                    continue;
                };

                source_id = self.source_id(&name);
                source_name = remote
                    .title()
                    .map(|t| self.source_id(&t))
                    .unwrap_or(source_id.clone());

                break;
            }
        }

        let mut extra = HashMap::new();
        if let Some(branch) = get_attr("Branch") {
            extra.insert("branch".to_string(), branch.to_string());
        }

        Ok(vec![Package {
            id: AppId::new(id),
            icon: widget::icon::from_name("package-x-generic")
                .size(128)
                .handle(),
            //TODO: fill in more AppInfo fields
            info: Arc::new(AppInfo {
                source_id,
                source_name,
                name: get_attr("Title").unwrap_or(id).to_string(),
                summary: get_attr("Comment").cloned().unwrap_or_default(),
                description: get_attr("Description").cloned().unwrap_or_default(),
                urls: get_attr("Homepage")
                    .map(|h| vec![AppUrl::Homepage(h.to_string())])
                    .unwrap_or_default(),
                package_paths: vec![path.to_string()],
                ..Default::default()
            }),
            version: String::new(),
            extra,
        }])
    }

    fn operation(
        &self,
        _op: &Operation,
        _callback: Box<dyn FnMut(f32) + 'static>,
    ) -> Result<crate::package::Tracked, Box<dyn Error>> {
        Err(crate::package::FLATPAK_UNAVAILABLE.into())
    }
}
