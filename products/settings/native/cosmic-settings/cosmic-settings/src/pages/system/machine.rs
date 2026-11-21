// SPDX-License-Identifier: GPL-3.0-only

use cosmic::widget::{button, settings, text};
use cosmic::{Apply, Task};
use cosmic_settings_page::{self as page, Section, section};
use serde::{Deserialize, Serialize};
use slotmap::SlotMap;

use crate::pages;

#[derive(Clone, Copy, Debug, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum Action {
    Status,
    EnableAutomaticLogin,
    DisableAutomaticLogin,
    CheckUpdates,
    PrepareUpdates,
    CancelUpdates,
    EnableAutomaticUpdates,
    DisableAutomaticUpdates,
    EnableAutomaticRestart,
    DisableAutomaticRestart,
    RestartForUpdates,
}

#[derive(Clone, Debug, Deserialize)]
pub struct State {
    current_user: String,
    automatic_login_user: Option<String>,
    updates: Updates,
}

#[derive(Clone, Debug, Deserialize)]
struct Updates {
    phase: String,
    checked_at: Option<String>,
    error: Option<String>,
    ready: bool,
    busy: bool,
    automatic_updates: bool,
    automatic_restart: bool,
    #[serde(default)]
    packages: Vec<Package>,
}

#[derive(Clone, Debug, Deserialize)]
struct Package {
    package: String,
    installed: String,
    version: String,
    held: bool,
}

#[derive(Clone, Debug)]
pub enum Message {
    Run(Action),
    Loaded(u64, Result<State, String>),
    Poll(u64),
    ConfirmRestart(bool),
}

#[derive(Clone, Debug, Default)]
pub struct MachinePage<const LOGIN: bool> {
    state: Option<State>,
    error: Option<String>,
    busy: bool,
    active: bool,
    revision: u64,
    confirm_restart: bool,
}

pub type SignInPage = MachinePage<true>;
pub type UpdatesPage = MachinePage<false>;

async fn request(action: Action) -> Result<State, String> {
    let action_name = serde_json::to_value(action).map_err(|error| error.to_string())?;
    let name = action_name
        .as_str()
        .ok_or("Invalid system settings action")?;
    let response = claw_os_sdk::cos_call_json_async_with_binary(
        "/usr/local/bin/cos",
        "settings",
        "system",
        ["__system-settings", name],
    )
    .await
    .map_err(|error| error.to_string())?;
    serde_json::from_value(response).map_err(|error| error.to_string())
}

fn message<const LOGIN: bool>(message: Message) -> pages::Message {
    pages::Message::MachineSettings(LOGIN, message)
}

impl<const LOGIN: bool> page::AutoBind<pages::Message> for MachinePage<LOGIN> {}

impl<const LOGIN: bool> page::Page<pages::Message> for MachinePage<LOGIN> {
    fn set_id(&mut self, _: page::Entity) {}

    fn content(
        &self,
        sections: &mut SlotMap<section::Entity, Section<pages::Message>>,
    ) -> Option<page::Content> {
        let content =
            Section::default().view::<Self>(|_, page, _| page.view().map(message::<LOGIN>));
        Some(vec![sections.insert(content)])
    }

    fn info(&self) -> page::Info {
        if LOGIN {
            page::Info::new("sign-in", "system-users-symbolic")
                .title(fl!("claw-sign-in"))
                .description(fl!("claw-sign-in-description"))
        } else {
            page::Info::new("system-updates", "system-software-update-symbolic")
                .title(fl!("claw-system-updates"))
                .description(fl!("claw-update-description"))
        }
    }

    fn on_enter(&mut self) -> Task<pages::Message> {
        self.active = true;
        if self.busy {
            Task::none()
        } else {
            self.start(Action::Status)
        }
    }

    fn on_leave(&mut self) -> Task<pages::Message> {
        self.active = false;
        self.confirm_restart = false;
        Task::none()
    }
}

impl<const LOGIN: bool> MachinePage<LOGIN> {
    fn start(&mut self, action: Action) -> Task<pages::Message> {
        self.busy = true;
        self.error = None;
        self.revision += 1;
        let revision = self.revision;
        Task::future(
            async move { message::<LOGIN>(Message::Loaded(revision, request(action).await)) },
        )
    }

    pub fn update(&mut self, input: Message) -> Task<pages::Message> {
        match input {
            Message::Run(action) if !self.busy => {
                self.confirm_restart = false;
                return self.start(action);
            }
            Message::Loaded(revision, result) if revision == self.revision => {
                self.busy = false;
                match result {
                    Ok(state) => {
                        let poll = self.active && !LOGIN && state.updates.busy;
                        self.state = Some(state);
                        if poll {
                            return Task::future(async move {
                                tokio::time::sleep(std::time::Duration::from_secs(2)).await;
                                message::<LOGIN>(Message::Poll(revision))
                            });
                        }
                    }
                    Err(error) => self.error = Some(error),
                }
            }
            Message::Poll(revision) if self.active && !self.busy && revision == self.revision => {
                return self.start(Action::Status);
            }
            Message::ConfirmRestart(confirm) => self.confirm_restart = confirm,
            _ => {}
        }
        Task::none()
    }

    fn view(&self) -> cosmic::Element<'_, Message> {
        let mut content = crate::widget::claw_list_column();
        if let Some(error) = &self.error {
            content = content.add(text::body(error));
        }
        if self.busy {
            content = content.add(text::caption(fl!("claw-settings-working")));
        }
        if let Some(state) = &self.state {
            if LOGIN {
                let description = match state.automatic_login_user.as_deref() {
                    Some(user) => fl!("claw-login-on", user = user),
                    None => fl!("claw-login-off"),
                };
                let (label, action) =
                    if state.automatic_login_user.as_deref() == Some(state.current_user.as_str()) {
                        (fl!("claw-login-disable"), Action::DisableAutomaticLogin)
                    } else {
                        (fl!("claw-login-enable"), Action::EnableAutomaticLogin)
                    };
                content = content
                    .add(text::body(fl!("claw-sign-in-description")))
                    .add(
                        settings::item::builder(fl!("claw-auto-login"))
                            .description(description)
                            .flex_control(self.button(label, action, !self.busy)),
                    );
                if state
                    .automatic_login_user
                    .as_deref()
                    .is_some_and(|user| user != state.current_user)
                {
                    content = content.add(self.button(
                        fl!("claw-login-disable"),
                        Action::DisableAutomaticLogin,
                        !self.busy,
                    ));
                }
            } else {
                let update = &state.updates;
                let enabled = !self.busy && !update.busy;
                content = content.add(text::body(update.status()));
                if let Some(time) = &update.checked_at {
                    content = content.add(text::caption(fl!(
                        "claw-update-checked",
                        time = time.as_str()
                    )));
                }
                if let Some(error) = &update.error {
                    content = content.add(text::body(error));
                }
                for package in &update.packages {
                    let versions = format!("{} → {}", package.installed, package.version);
                    let note = if package.held {
                        fl!("claw-update-held", versions = versions.as_str())
                    } else {
                        versions
                    };
                    content = content.add(settings::flex_item(&package.package, text::body(note)));
                }
                if update.ready {
                    content = content.add(text::body(fl!("claw-update-save-work")));
                    if self.confirm_restart {
                        content = content
                            .add(self.button(
                                fl!("claw-update-restart"),
                                Action::RestartForUpdates,
                                enabled,
                            ))
                            .add(
                                button::standard(fl!("cancel"))
                                    .on_press(Message::ConfirmRestart(false)),
                            );
                    } else {
                        content = content
                            .add(
                                button::suggested(fl!("claw-update-restart")).on_press_maybe(
                                    enabled.then_some(Message::ConfirmRestart(true)),
                                ),
                            )
                            .add(self.button(
                                fl!("claw-update-cancel"),
                                Action::CancelUpdates,
                                enabled,
                            ));
                    }
                } else {
                    content = content.add(self.button(
                        fl!("claw-update-check"),
                        Action::CheckUpdates,
                        enabled,
                    ));
                    if update.phase == "available"
                        && !update.packages.iter().any(|package| package.held)
                    {
                        content = content.add(self.button(
                            fl!("claw-update-download"),
                            Action::PrepareUpdates,
                            enabled,
                        ));
                    }
                }
                for (title, help, is_on, on, off, available) in [
                    (
                        fl!("claw-update-automatic"),
                        fl!("claw-update-automatic-help"),
                        update.automatic_updates,
                        Action::EnableAutomaticUpdates,
                        Action::DisableAutomaticUpdates,
                        true,
                    ),
                    (
                        fl!("claw-update-auto-restart"),
                        fl!("claw-update-auto-restart-help"),
                        update.automatic_restart,
                        Action::EnableAutomaticRestart,
                        Action::DisableAutomaticRestart,
                        update.automatic_updates,
                    ),
                ] {
                    let label = if is_on {
                        fl!("claw-setting-turn-off")
                    } else {
                        fl!("claw-setting-turn-on")
                    };
                    let action = if is_on { off } else { on };
                    content = content.add(
                        settings::item::builder(title)
                            .description(help)
                            .flex_control(self.button(label, action, enabled && available)),
                    );
                }
            }
        } else if !self.busy {
            content = content.add(self.button(fl!("claw-settings-refresh"), Action::Status, true));
        }
        content.apply(cosmic::Element::from)
    }

    fn button(&self, label: String, action: Action, enabled: bool) -> cosmic::Element<'_, Message> {
        button::standard(label)
            .on_press_maybe(enabled.then_some(Message::Run(action)))
            .into()
    }
}

impl Updates {
    fn status(&self) -> String {
        if self.ready {
            return fl!("claw-update-ready");
        }
        match self.phase.as_str() {
            "checking" => fl!("claw-update-checking"),
            "available" => fl!("claw-update-available"),
            "up-to-date" => fl!("claw-update-current"),
            "downloading" => fl!("claw-update-downloading"),
            "installed" => fl!("claw-update-installed"),
            "failed" | "install-failed" | "interrupted" => fl!("claw-update-failed"),
            _ if self.busy => fl!("claw-settings-working"),
            _ => fl!("claw-update-unchecked"),
        }
    }
}
