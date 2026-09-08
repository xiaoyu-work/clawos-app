// SPDX-License-Identifier: GPL-3.0-only
use cosmic::widget::{button, column, dropdown, row, text};
use cosmic::{Element, Task};
use serde::Deserialize;
use serde_json::{Value, json};

#[derive(Clone, Debug)]
pub enum Message {
    Refresh,
    Select(usize),
    Change(String, bool),
    Decide(String, bool),
    Cancel,
    Loaded(u64, String, Result<Value, String>),
}

#[derive(Default)]
pub struct State {
    apps: Vec<String>,
    selected: Option<usize>,
    details: Option<Details>,
    busy: bool,
    epoch: u64,
    handle: Option<cosmic::iced::task::Handle>,
    error: Option<String>,
    notice: Option<String>,
    quarantined: Vec<Value>,
}

#[derive(Debug, Deserialize)]
struct Catalog {
    apps: Vec<App>,
    quarantined: Vec<Value>,
    truncated: bool,
}

#[derive(Debug, Deserialize)]
struct App {
    app_id: String,
}

#[derive(Debug, Deserialize)]
struct Details {
    app_id: String,
    trust: String,
    permissions: Vec<Permission>,
    pending: Vec<Pending>,
    recent: Vec<Value>,
    semantics: String,
}

#[derive(Debug, Deserialize)]
struct Permission {
    permission_id: String,
    declared: Value,
    capability: Option<Value>,
    manageable: bool,
    enabled: Option<bool>,
    live_granted: Option<bool>,
    limitation: Option<String>,
}

#[derive(Debug, Deserialize)]
struct Pending {
    id: String,
    verb: String,
    scope: Value,
    reason: String,
}

impl State {
    pub fn cancel(&mut self) {
        if let Some(handle) = self.handle.take() {
            handle.abort();
        }
        self.epoch = self.epoch.wrapping_add(1);
        self.busy = false;
    }

    fn start(&mut self, action: &str, request: Value) -> Task<Message> {
        self.cancel();
        self.busy = true;
        self.error = None;
        let epoch = self.epoch;
        let action = action.to_string();
        let (task, handle) = Task::future(async move {
            let result = crate::permissions::call(request).await;
            Message::Loaded(epoch, action, result)
        })
        .abortable();
        self.handle = Some(handle);
        task
    }

    fn reload_selected(&mut self) -> Task<Message> {
        match self
            .selected
            .and_then(|index| self.apps.get(index))
            .cloned()
        {
            Some(app) => self.start("show", json!({"action":"show", "app_id":app})),
            None => Task::none(),
        }
    }

    pub fn update(&mut self, message: Message) -> Task<Message> {
        match message {
            Message::Cancel => {
                self.cancel();
                self.notice = Some(crate::fl!("app-permissions-cancelled"));
            }
            Message::Refresh => return self.start("list", json!({"action":"list"})),
            Message::Select(index) if index < self.apps.len() => {
                self.selected = Some(index);
                self.details = None;
                return self.reload_selected();
            }
            Message::Change(key, enable) if !self.busy => {
                if let Some(details) = &self.details {
                    if !details
                        .permissions
                        .iter()
                        .any(|permission| permission.permission_id == key && permission.manageable)
                    {
                        self.error = Some(crate::fl!("app-permissions-unsupported"));
                        return Task::none();
                    }
                    let action = if enable { "request" } else { "revoke" };
                    let request = crate::permissions::request(action, &details.app_id, &key);
                    return self.start(action, request);
                }
            }
            Message::Decide(id, approve) if !self.busy => {
                if !self
                    .details
                    .as_ref()
                    .is_some_and(|details| details.pending.iter().any(|request| request.id == id))
                {
                    self.error = Some(crate::fl!("app-permissions-stale"));
                    return Task::none();
                }
                self.cancel();
                self.busy = true;
                let epoch = self.epoch;
                let (task, handle) = Task::future(async move {
                    Message::Loaded(
                        epoch,
                        "decide".into(),
                        crate::permissions::decide(id, approve).await,
                    )
                })
                .abortable();
                self.handle = Some(handle);
                return task;
            }
            Message::Loaded(epoch, action, result) if epoch == self.epoch => {
                self.busy = false;
                self.handle = None;
                match result {
                    Err(error) => self.error = Some(error),
                    Ok(value) if action == "list" => match serde_json::from_value::<Catalog>(value)
                    {
                        Ok(catalog) => {
                            self.apps = catalog.apps.into_iter().map(|app| app.app_id).collect();
                            self.quarantined = catalog.quarantined;
                            self.selected = (!self.apps.is_empty()).then_some(0);
                            self.details = None;
                            self.notice = catalog
                                .truncated
                                .then(|| crate::fl!("app-permissions-truncated"));
                            return self.reload_selected();
                        }
                        Err(error) => {
                            self.error = Some(format!("Invalid permission catalog: {error}"))
                        }
                    },
                    Ok(value) if action == "show" => match serde_json::from_value::<Details>(value)
                    {
                        Ok(details) => self.details = Some(details),
                        Err(error) => {
                            self.error = Some(format!("Invalid permission state: {error}"))
                        }
                    },
                    Ok(_) => {
                        self.notice = Some(if action == "request" {
                            crate::fl!("app-permissions-pending")
                        } else {
                            crate::fl!("app-permissions-refresh-after-change")
                        });
                        return self.reload_selected();
                    }
                }
            }
            _ => {}
        }
        Task::none()
    }

    pub fn view(&self) -> Element<'_, Message> {
        let mut content = column::with_capacity(16)
            .spacing(12)
            .push(text::title3(crate::fl!("app-permissions")))
            .push(text::body(crate::fl!("app-permissions-description")));
        content = content.push(
            row::with_capacity(2)
                .spacing(12)
                .push(
                    button::standard(crate::fl!("app-permissions-refresh"))
                        .on_press(Message::Refresh),
                )
                .push(
                    button::standard(crate::fl!("app-permissions-cancel"))
                        .on_press(Message::Cancel),
                ),
        );
        if self.busy {
            content = content.push(text::body(crate::fl!("app-permissions-loading")));
        }
        if let Some(error) = &self.error {
            content = content.push(text::body(error));
        }
        if let Some(notice) = &self.notice {
            content = content.push(text::body(notice));
        }
        if !self.apps.is_empty() {
            content = content.push(dropdown(&self.apps, self.selected, Message::Select));
        } else if !self.busy {
            content = content.push(text::body(crate::fl!("app-permissions-empty")));
        }
        for entry in &self.quarantined {
            content = content.push(text::body(format!(
                "{}: {entry}",
                crate::fl!("app-permissions-quarantined")
            )));
        }
        if let Some(details) = &self.details {
            content = content
                .push(text::body(format!(
                    "{} ({})",
                    details.app_id, details.trust
                )))
                .push(text::body(&details.semantics));
            for permission in &details.permissions {
                let title = permission
                    .capability
                    .as_ref()
                    .unwrap_or(&permission.declared)
                    .to_string();
                let enabled = state_label(permission.enabled);
                let live = state_label(permission.live_granted);
                content = content
                    .push(text::body(title))
                    .push(text::body(format!(
                        "{}: {enabled}; {}: {live}",
                        crate::fl!("app-permissions-enabled"),
                        crate::fl!("app-permissions-live")
                    )))
                    .push(text::body(permission.declared.to_string()));
                if permission.manageable && !self.busy {
                    if let Some(enabled) = permission.enabled {
                        content = content.push(
                            button::standard(if enabled {
                                crate::fl!("app-permissions-revoke")
                            } else {
                                crate::fl!("app-permissions-request")
                            })
                            .on_press(Message::Change(permission.permission_id.clone(), !enabled)),
                        );
                    }
                } else if let Some(limitation) = &permission.limitation {
                    content = content.push(text::body(limitation));
                }
            }
            content = content.push(text::title4(crate::fl!("app-permissions-pending-title")));
            for request in &details.pending {
                content = content.push(text::body(format!(
                    "{}: {} {} — {}",
                    request.id, request.verb, request.scope, request.reason
                )));
                if !self.busy {
                    content = content.push(
                        row::with_capacity(2)
                            .spacing(12)
                            .push(
                                button::standard(crate::fl!("app-permissions-approve"))
                                    .on_press(Message::Decide(request.id.clone(), true)),
                            )
                            .push(
                                button::standard(crate::fl!("app-permissions-deny"))
                                    .on_press(Message::Decide(request.id.clone(), false)),
                            ),
                    );
                }
            }
            content = content.push(text::title4(crate::fl!("app-permissions-recent")));
            for recent in &details.recent {
                content = content.push(text::body(recent.to_string()));
            }
        }
        content.into()
    }
}

fn state_label(value: Option<bool>) -> String {
    match value {
        Some(true) => crate::fl!("app-permissions-yes"),
        Some(false) => crate::fl!("app-permissions-no"),
        None => crate::fl!("app-permissions-unknown"),
    }
}

#[cfg(test)]
mod tests {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/unit/applications_permissions.rs"
    ));
}
