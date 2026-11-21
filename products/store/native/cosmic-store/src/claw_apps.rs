use std::sync::Arc;

use cosmic::{Element, iced::Length, widget};
use serde::Deserialize;
use serde_json::json;

use crate::{App, AppId, AppInfo, Message, OperationKind, backend::BackendName, fl};

pub(crate) const SOURCE_ID: &str = "claw-apps";

#[derive(Clone, Debug, Deserialize)]
pub(crate) struct Catalog {
    pub apps: Vec<Release>,
    pub checked_at: Option<String>,
}

#[derive(Clone, Debug, Deserialize)]
pub(crate) struct Release {
    pub id: String,
    pub name: String,
    pub description: String,
    pub package: String,
    pub released: String,
    pub installed: Option<String>,
    pub update: bool,
}

pub(crate) fn load() -> Result<Catalog, String> {
    let value = crate::product::query("store", json!({})).map_err(|error| error.to_string())?;
    serde_json::from_value(value).map_err(|error| error.to_string())
}

impl App {
    pub(crate) fn source_check_button(&self) -> Element<'_, Message> {
        let mut check = widget::button::standard(if self.refreshing_sources {
            fl!("checking-for-updates")
        } else {
            fl!("check-for-updates")
        });
        if !self.refreshing_sources && self.pending_operations.is_empty() {
            check = check.on_press(Message::CheckUpdates);
        }
        check.into()
    }

    pub(crate) fn claw_apps_view(&self, updates: bool) -> Element<'_, Message> {
        let mut column = widget::column::with_capacity(4)
            .spacing(12)
            .width(Length::Fill);
        if let Some(result) = &self.claw_catalog {
            match result {
                Ok(catalog) => {
                    let query = if !updates && self.search_active {
                        self.search_input.trim().to_lowercase()
                    } else {
                        String::new()
                    };
                    let mut shown = std::collections::HashSet::new();
                    let mut rows = catalog
                        .apps
                        .iter()
                        .filter(|app| !updates || app.update)
                        .filter(|app| {
                            query.is_empty()
                                || app.name.to_lowercase().contains(&query)
                                || app.id.contains(&query)
                        })
                        .collect::<Vec<_>>();
                    rows.sort_by(|left, right| {
                        crate::LANGUAGE_SORTER.compare(&left.name, &right.name)
                    });
                    if rows.is_empty() {
                        return column
                            .push(widget::text::body(if updates {
                                fl!("claw-no-updates")
                            } else if query.is_empty() {
                                fl!("claw-no-apps")
                            } else {
                                fl!("no-results", search = self.search_input.trim())
                            }))
                            .into();
                    }
                    for app in rows {
                        if updates && !shown.insert(&app.package) {
                            continue;
                        }
                        let status = match &app.installed {
                            Some(current) if current == &app.released => {
                                fl!("claw-installed", version = current.as_str())
                            }
                            Some(current) => fl!(
                                "claw-version-pair",
                                current = current.as_str(),
                                available = app.released.as_str()
                            ),
                            None => fl!("claw-release", version = app.released.as_str()),
                        };
                        let mut row = widget::row::with_capacity(2)
                            .spacing(12)
                            .align_y(cosmic::iced::Alignment::Center);
                        row = row.push(
                            widget::column::with_capacity(3)
                                .spacing(3)
                                .width(Length::Fill)
                                .push(widget::text::heading(app.name.as_str()))
                                .push(widget::text::body(app.description.as_str()))
                                .push(widget::text::caption(status)),
                        );
                        if app.installed.is_none() || app.update {
                            let info = Arc::new(AppInfo {
                                source_id: SOURCE_ID.into(),
                                source_name: fl!("claw-apps"),
                                name: app.name.clone(),
                                pkgnames: vec![app.package.clone()],
                                releases: vec![crate::app_info::AppRelease {
                                    version: app.released.clone(),
                                    timestamp: None,
                                    description: None,
                                    url: None,
                                }],
                                ..AppInfo::default()
                            });
                            let (label, kind) = if app.update {
                                (fl!("update"), OperationKind::Update)
                            } else {
                                (fl!("install"), OperationKind::Install)
                            };
                            row = row.push(widget::button::standard(label).on_press(
                                Message::Operation(
                                    kind,
                                    BackendName::Packagekit,
                                    AppId::new(&app.id),
                                    info,
                                ),
                            ));
                        }
                        column = column.push(row);
                    }
                }
                Err(error) => {
                    column = column.push(widget::text::body(fl!(
                        "claw-catalog-unavailable",
                        error = error.as_str()
                    )));
                }
            }
        } else {
            column = column.push(widget::text::body(fl!("claw-catalog-loading")));
        }
        column.into()
    }
}
