use cosmic::widget;
use packagekit_zbus::{
    package_kit::PackageKitProxyBlocking,
    transaction::TransactionProxyBlocking,
    zbus::{
        MatchRule,
        blocking::{Connection, MessageIterator},
        message::Type,
        zvariant,
    },
};
use std::{collections::HashMap, error::Error, fmt::Write, sync::Arc};

use super::{Backend, Package};
use crate::{AppId, AppInfo, AppUrl, AppstreamCache, GStreamerCodec, Operation};

#[derive(Debug)]
struct TransactionDetails {
    //TODO: more fields: https://www.freedesktop.org/software/PackageKit/gtk-doc/Transaction.html#Transaction::Details
    package_id: String,
    summary: String,
    description: String,
    url: String,
}

#[allow(dead_code)]
#[derive(Debug)]
struct TransactionPackage {
    info: u32,
    package_id: String,
    summary: String,
}

#[allow(dead_code)]
struct TransactionProgress {
    package_id: String,
    status: u32,
    percentage: u32,
}

fn transaction_handle(
    tx: TransactionProxyBlocking,
    mut on_progress: impl FnMut(u32, TransactionProgress),
) -> Result<(Vec<TransactionDetails>, Vec<TransactionPackage>), Box<dyn Error>> {
    let mut details = Vec::new();
    let mut packages = Vec::new();
    let inner = tx.inner();
    let rule = MatchRule::builder()
        .msg_type(Type::Signal)
        .interface("org.freedesktop.PackageKit.Transaction")?
        .path(inner.path())?
        .build();
    let iter = MessageIterator::for_match_rule(rule, inner.connection(), None)?;

    for result in iter {
        let signal = result?;
        if let Some(member) = signal.header().member() {
            match member.as_str() {
                "Details" => {
                    let map = signal
                        .body()
                        .deserialize::<HashMap<String, zvariant::OwnedValue>>()?;
                    let get_string = |key: &str| -> Option<String> {
                        match map.get(key).map(|v| &**v) {
                            Some(zvariant::Value::Str(str)) => Some(str.to_string()),
                            unknown => {
                                log::warn!(
                                    "failed to find string for key {:?} in packagekit Details: found {:?} instead",
                                    key,
                                    unknown
                                );
                                None
                            }
                        }
                    };

                    let Some(package_id) = get_string("package-id") else {
                        continue;
                    };
                    let summary = get_string("summary").unwrap_or_default();
                    let description = get_string("description").unwrap_or_default();
                    let url = get_string("url").unwrap_or_default();
                    details.push(TransactionDetails {
                        package_id,
                        summary,
                        description,
                        url,
                    });
                }
                "ErrorCode" => {
                    // https://www.freedesktop.org/software/PackageKit/gtk-doc/Transaction.html#Transaction::ErrorCode
                    let (code, details) = signal.body().deserialize::<(u32, String)>()?;
                    if code != 48 {
                        return Err(format!("{details} (code {code})").into());
                    }
                }
                "ItemProgress" => {
                    // https://www.freedesktop.org/software/PackageKit/gtk-doc/Transaction.html#Transaction::ItemProgress
                    let (package_id, status, percentage) =
                        signal.body().deserialize::<(String, u32, u32)>()?;
                    let total_percentage = tx.percentage().unwrap_or(percentage);
                    on_progress(
                        total_percentage,
                        TransactionProgress {
                            package_id,
                            status,
                            percentage,
                        },
                    );
                }
                "Package" => {
                    // https://www.freedesktop.org/software/PackageKit/gtk-doc/Transaction.html#Transaction::Package
                    let (info, package_id, summary) =
                        signal.body().deserialize::<(u32, String, String)>()?;
                    packages.push(TransactionPackage {
                        info,
                        package_id,
                        summary,
                    });
                }
                "Finished" => break,
                _ => {
                    log::warn!("unknown signal {}", member);
                }
            }
        }
    }
    Ok((details, packages))
}

// https://lazka.github.io/pgi-docs/PackageKitGlib-1.0/enums.html#PackageKitGlib.FilterEnum
#[repr(u64)]
enum FilterKind {
    None = 1 << 1,
    Installed = 1 << 2,
    Newest = 1 << 16,
    Arch = 1 << 18,
}

#[derive(Debug)]
pub struct Packagekit {
    connection: Connection,
    appstream_caches: Vec<AppstreamCache>,
}

impl Packagekit {
    pub fn new(locale: &str) -> Result<Self, Box<dyn Error>> {
        //TODO: cache more zbus stuff?
        let connection = Connection::system()?;
        let source_id = "packagekit";
        //TODO: translate?
        let source_name = "System";
        Ok(Self {
            connection,
            appstream_caches: vec![AppstreamCache::system(
                source_id.to_string(),
                source_name.to_string(),
                locale,
            )],
        })
    }

    fn transaction(&self) -> Result<TransactionProxyBlocking<'_>, Box<dyn Error>> {
        //TODO: use async?
        let pk = PackageKitProxyBlocking::new(&self.connection)?;
        //TODO: set locale?
        let tx_path = pk.create_transaction()?;
        let tx = TransactionProxyBlocking::builder(&self.connection)
            .destination("org.freedesktop.PackageKit")?
            .path(tx_path)?
            .build()?;
        tx.set_hints(&["interactive=false"])?;
        Ok(tx)
    }

    fn package_transaction(
        &self,
        tx: TransactionProxyBlocking,
    ) -> Result<Vec<Package>, Box<dyn Error>> {
        let appstream_cache = &self.appstream_caches[0];

        let (tx_details, tx_packages) = transaction_handle(tx, |_, _| {})?;

        let mut system_packages = Vec::new();
        let mut packages = Vec::new();

        for tx_detail in tx_details {
            //TODO: this is a hack to handle file details like they are packages
            let mut parts = tx_detail.package_id.split(';');
            let Some(package_name) = parts.next() else {
                continue;
            };
            let version_opt = parts.next();
            let _architecture_opt = parts.next();

            let data = parts.next().unwrap_or("");
            let mut data_parts = data.split(':');
            let _status_opt = data_parts.next();
            let _origin_opt = data_parts.next();

            //TODO: translate
            packages.push(Package {
                id: AppId::new(package_name),
                icon: widget::icon::from_name("package-x-generic")
                    .size(128)
                    .handle(),
                //TODO: fill in more AppInfo fields
                info: Arc::new(AppInfo {
                    source_id: appstream_cache.source_id.clone(),
                    source_name: appstream_cache.source_name.clone(),
                    name: package_name.to_string(),
                    summary: tx_detail.summary.clone(),
                    description: tx_detail.description.clone(),
                    pkgnames: vec![package_name.to_string()],
                    urls: if !tx_detail.url.is_empty() {
                        vec![AppUrl::Homepage(tx_detail.url)]
                    } else {
                        Vec::new()
                    },
                    ..Default::default()
                }),
                version: version_opt.unwrap_or("").to_string(),
                extra: HashMap::new(),
            });
        }

        for tx_package in tx_packages {
            let mut parts = tx_package.package_id.split(';');
            let Some(package_name) = parts.next() else {
                continue;
            };
            let version_opt = parts.next();
            let _architecture_opt = parts.next();

            let data = parts.next().unwrap_or("");
            let mut data_parts = data.split(':');
            let _status_opt = data_parts.next();
            let _origin_opt = data_parts.next();

            match appstream_cache.pkgnames.get(package_name) {
                Some(ids) => {
                    for id in ids.iter() {
                        match appstream_cache.infos.get(id) {
                            Some(info) => {
                                packages.push(Package {
                                    id: id.clone(),
                                    icon: appstream_cache.icon(info),
                                    info: info.clone(),
                                    version: version_opt.unwrap_or("").to_string(),
                                    extra: HashMap::new(),
                                });
                            }
                            None => {
                                log::warn!("failed to find info {:?}", id);
                            }
                        }
                    }
                }
                None => {
                    // Ignore packages with no components
                    log::debug!("no components for package {}", package_name);
                    system_packages.push((
                        package_name.to_string(),
                        version_opt.unwrap_or("").to_string(),
                    ));
                }
            }
        }
        if !system_packages.is_empty() {
            let name = crate::fl!("system-packages");
            let summary = crate::fl!("system-packages-summary", count = system_packages.len());
            let mut description = String::new();
            let mut pkgnames = Vec::with_capacity(system_packages.len());
            let mut extra = HashMap::new();
            for (package_name, version) in system_packages {
                let _ = writeln!(description, " * {}: {}", package_name, version);
                // Store update version in extra for UI display
                extra.insert(format!("{}_update", package_name), version);
                pkgnames.push(package_name);
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
        for appstream_cache in self.appstream_caches.iter_mut() {
            appstream_cache.reload();
        }
        Ok(())
    }

    fn info_caches(&self) -> &[AppstreamCache] {
        &self.appstream_caches
    }

    fn installed(&self) -> Result<Vec<Package>, Box<dyn Error>> {
        let tx = self.transaction()?;
        tx.get_packages(FilterKind::Installed as u64)?;
        self.package_transaction(tx)
    }

    fn updates(&self) -> Result<Vec<Package>, Box<dyn Error>> {
        let tx = self.transaction()?;
        tx.get_updates(FilterKind::None as u64)?;
        let mut packages = self.package_transaction(tx)?;

        // For system packages, fetch current installed versions
        for package in packages.iter_mut() {
            if package.id.is_system() && !package.info.pkgnames.is_empty() {
                // Get current installed versions for all system packages
                let tx = self.transaction()?;
                tx.resolve(
                    FilterKind::Installed as u64,
                    &package
                        .info
                        .pkgnames
                        .iter()
                        .map(|s| s.as_str())
                        .collect::<Vec<_>>(),
                )?;
                let (_tx_details, tx_packages) = transaction_handle(tx, |_, _| {})?;

                // Build a map of package name to installed version
                for tx_package in tx_packages {
                    let mut parts = tx_package.package_id.split(';');
                    if let Some(pkg_name) = parts.next()
                        && let Some(version) = parts.next()
                    {
                        package
                            .extra
                            .insert(format!("{}_installed", pkg_name), version.to_string());
                    }
                }
            }
        }

        Ok(packages)
    }

    fn file_packages(&self, path: &str) -> Result<Vec<Package>, Box<dyn Error>> {
        let path = crate::claw_glue::read_path(std::path::Path::new(path))
            .map_err(|error| -> Box<dyn Error> { crate::claw_glue::user_message(&error).into() })?;
        let path = path.to_str().ok_or("package metadata path must be UTF-8")?;
        let tx = self.transaction()?;
        tx.get_details_local(&[path])?;
        let mut packages = self.package_transaction(tx)?;
        for package in packages.iter_mut() {
            let info = Arc::make_mut(&mut package.info);
            info.package_paths.push(path.to_string());
        }
        Ok(packages)
    }

    fn gstreamer_packages(
        &self,
        gstreamer_codec: &GStreamerCodec,
    ) -> Result<Vec<Package>, Box<dyn Error>> {
        // Packagekit provides looks like gstreamer1.0(decoder-video/x-h264)
        //TODO: truncate version ending in .0? gstreamer1.0-packagekit does this but it does not appear to be required
        let provides = format!(
            "gstreamer{}({})",
            gstreamer_codec.version, gstreamer_codec.type_name
        );
        let tx = self.transaction()?;
        tx.what_provides(
            FilterKind::Newest as u64 | FilterKind::Arch as u64,
            &[&provides],
        )?;
        let (_tx_details, tx_packages) = transaction_handle(tx, |_, _| {})?;

        // Convert packages to details in order to show more information
        let package_ids = tx_packages
            .iter()
            .map(|p| p.package_id.as_str())
            .collect::<Vec<_>>();
        let tx = self.transaction()?;
        tx.get_details(&package_ids)?;
        self.package_transaction(tx)
    }

    fn operation(
        &self,
        op: &Operation,
        _f: Box<dyn FnMut(f32) + 'static>,
    ) -> Result<crate::package::Tracked, Box<dyn Error>> {
        Ok(crate::package::submit(op)?)
    }
}
