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
    revision: String,
    permissions: Vec<Permission>,
}

#[derive(Debug, Deserialize)]
struct Permission {
    permission_id: String,
    label: String,
    description: String,
    target: String,
    enabled: Option<bool>,
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
        self.details = None;
        match self
            .selected
            .and_then(|index| self.apps.get(index))
            .cloned()
        {
            Some(app) => self.start("show_choices", json!({"action":"show_choices", "app_id":app})),
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
                        .any(|permission| permission.permission_id == key)
                    {
                        self.error = Some(crate::fl!("app-permissions-unsupported"));
                        return Task::none();
                    }
                    let action = if enable { "allow" } else { "deny" };
                    let request = crate::permissions::choice(
                        enable, &details.app_id, &key, &details.revision,
                    );
                    return self.start(action, request);
                }
            }
            Message::Loaded(epoch, action, result) if epoch == self.epoch => {
                self.busy = false;
                self.handle = None;
                match result {
                    Err(error) => self.error = Some(error),
                    Ok(value) if action == "list" => match serde_json::from_value::<Catalog>(value)
                    {
                        Ok(catalog) => {
                            let selected = self
                                .selected
                                .and_then(|index| self.apps.get(index))
                                .cloned();
                            self.apps = catalog.apps.into_iter().map(|app| app.app_id).collect();
                            self.quarantined = catalog.quarantined;
                            self.selected = selected
                                .and_then(|app| self.apps.iter().position(|id| *id == app))
                                .or_else(|| (!self.apps.is_empty()).then_some(0));
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
                    Ok(value) if action == "show_choices" => {
                        match serde_json::from_value::<Details>(value) {
                            Ok(details)
                                if self.selected.and_then(|index| self.apps.get(index))
                                    == Some(&details.app_id) =>
                            {
                                self.details = Some(details);
                            }
                            Ok(_) => {
                                self.details = None;
                                self.error = Some("OS permission state belongs to a different App; refresh Settings.".into());
                            }
                            Err(error) => {
                                self.details = None;
                                self.error = Some(format!("Invalid permission state: {error}"))
                            }
                        }
                    }
                    Ok(_) if action == "allow" || action == "deny" => {
                        self.notice = Some(crate::fl!("app-permissions-refresh-after-change"));
                        return self.reload_selected();
                    }
                    Ok(_) => {
                        self.error = Some(
                            "Unexpected App permission service action; refresh Settings.".into(),
                        );
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
            if details.permissions.is_empty() {
                content = content.push(text::body(crate::fl!("app-permissions-no-choices")));
            }
            for permission in &details.permissions {
                let selection = match permission.enabled {
                    Some(true) => crate::fl!("app-permissions-request"),
                    Some(false) => crate::fl!("app-permissions-revoke"),
                    None => crate::fl!("app-permissions-unknown"),
                };
                content = content
                    .push(text::title4(&permission.label))
                    .push(text::body(&permission.description))
                    .push(text::body(&permission.target))
                    .push(text::body(selection));
                if !self.busy {
                    let mut buttons = row::with_capacity(2).spacing(8);
                    if permission.enabled != Some(true) {
                        buttons = buttons.push(button::standard(crate::fl!("app-permissions-request"))
                            .on_press(Message::Change(permission.permission_id.clone(), true)));
                    }
                    if permission.enabled != Some(false) {
                        buttons = buttons.push(button::standard(crate::fl!("app-permissions-revoke"))
                            .on_press(Message::Change(permission.permission_id.clone(), false)));
                    }
                    content = content.push(buttons);
                }
            }
        }
        content.into()
    }
}

#[cfg(test)]
mod tests {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/unit/applications_permissions.rs"
    ));
}
