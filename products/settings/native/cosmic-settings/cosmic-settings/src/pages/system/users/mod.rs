// Copyright 2024 System76 <info@system76.com>
// SPDX-License-Identifier: GPL-3.0-only

use crate::{
    pages,
    regional_settings::{Failure, Pending},
    user_settings::{self, Change, Target, DEFAULT_ICON_FILE},
};
use cosmic::{
    Apply, Element,
    dialog::file_chooser,
    iced::{Alignment, Length},
    widget::{self, column, icon, list, row, settings, space::horizontal, text},
};
use cosmic_settings_page::{self as page, Section, section};
use slotmap::SlotMap;
use std::{path::PathBuf, sync::Arc};
use url::Url;

#[derive(Clone, Debug, Default)]
pub struct User {
    id: u32,
    account_name: String,
    profile_icon: Option<icon::Handle>,
    full_name: String,
    username: String,
    credential: String,
    credential_confirm: String,
    full_name_edit: bool,
    username_edit: bool,
    is_admin: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum EditorField {
    FullName,
    Username,
}

#[derive(Clone, Debug)]
pub enum Dialog {
    AddNewUser(User),
    UpdatePassword(User),
}

#[derive(Clone, Debug)]
pub struct Page {
    on_enter_handle: Option<cosmic::iced::task::Handle>,
    entity: page::Entity,
    users: Vec<User>,
    selected_user_idx: Option<usize>,
    dialog: Option<Dialog>,
    default_icon: icon::Handle,
    password_label: String,
    credential_label: String,
    credential_confirm_label: String,
    username_label: String,
    fullname_label: String,
    pending: Pending,
    query_generation: u64,
    last_outcome: Option<String>,
    notice: Option<String>,
}

impl Default for Page {
    fn default() -> Self {
        Self {
            on_enter_handle: None,
            entity: page::Entity::default(),
            users: Vec::default(),
            selected_user_idx: None,
            dialog: None,
            default_icon: icon::from_path(PathBuf::from(DEFAULT_ICON_FILE)),
            password_label: crate::fl!("password"),
            credential_label: crate::fl!("users-password-credential"),
            credential_confirm_label: crate::fl!("users-password-credential-confirm"),
            username_label: crate::fl!("username"),
            fullname_label: crate::fl!("full-name"),
            pending: Pending::default(),
            query_generation: 0,
            last_outcome: None,
            notice: None,
        }
    }
}
#[derive(Clone, Debug)]
pub enum Message {
    ApplyEdit(usize, EditorField),
    Dialog(Option<Dialog>),
    Edit(usize, EditorField, String),
    LoadPage(u64, (u64, bool), Result<Vec<User>, Failure>),
    Finished(u64, Result<(), Failure>),
    NewUser(String, String, String, bool),
    None,
    Refresh,
    SelectProfileImage(u32),
    SelectedProfileImage(u32, Arc<Result<Url, file_chooser::Error>>),
    SelectUser(usize),
    SelectedUserDelete(u32),
    SelectedUserSetAdmin(u32, bool),
    ToggleEdit(usize, EditorField),
    SaveNewPassword(User),
}

impl From<Message> for crate::app::Message {
    fn from(message: Message) -> Self {
        crate::pages::Message::User(message).into()
    }
}

impl From<Message> for crate::pages::Message {
    fn from(message: Message) -> Self {
        crate::pages::Message::User(message)
    }
}

impl page::Page<crate::pages::Message> for Page {
    fn set_id(&mut self, entity: page::Entity) {
        self.entity = entity;
    }

    fn content(
        &self,
        sections: &mut SlotMap<section::Entity, Section<crate::pages::Message>>,
    ) -> Option<page::Content> {
        Some(vec![sections.insert(user_list())])
    }

    fn info(&self) -> page::Info {
        page::Info::new("users", "system-users-symbolic")
            .title(fl!("users"))
            .description(fl!("xdg-entry-users-comment"))
    }

    fn dialog(&self) -> Option<Element<'_, pages::Message>> {
        let dialog = self.dialog.as_ref()?;

        let dialog_element = match dialog {
            Dialog::AddNewUser(user) => {
                let full_name_input = widget::container(
                    widget::text_input("", &user.full_name)
                        .label(&self.fullname_label)
                        .on_input(|value| {
                            Message::Dialog(Some(Dialog::AddNewUser(User {
                                full_name: value,
                                ..user.clone()
                            })))
                        }),
                );

                let username_input = widget::container(
                    widget::text_input("", &user.username)
                        .label(&self.username_label)
                        .on_input(|value| {
                            Message::Dialog(Some(Dialog::AddNewUser(User {
                                username: value,
                                ..user.clone()
                            })))
                        }),
                );

                let credential_input = widget::container(
                    widget::text_input("", &user.credential)
                        .label(&self.credential_label)
                        .on_input(|value| {
                            Message::Dialog(Some(Dialog::AddNewUser(User {
                                credential: value,
                                ..user.clone()
                            })))
                        }),
                );

                let credential_confirm_input = widget::container(
                    widget::text_input("", &user.credential_confirm)
                        .label(&self.credential_confirm_label)
                        .on_input(|value| {
                            Message::Dialog(Some(Dialog::AddNewUser(User {
                                credential_confirm: value,
                                ..user.clone()
                            })))
                        }),
                );

                let admin_toggler = widget::toggler(user.is_admin).on_toggle(|value| {
                    Message::Dialog(Some(Dialog::AddNewUser(User {
                        is_admin: value,
                        ..user.clone()
                    })))
                });

                let mut validation_msg = String::new();
                let username_valid = user_settings::valid_name(&user.username);
                let complete_maybe = if !username_valid && !user.username.is_empty() {
                    validation_msg = fl!("invalid-username");
                    None
                } else if user.credential != user.credential_confirm
                    && !user.credential.is_empty()
                    && !user.credential_confirm.is_empty()
                {
                    validation_msg = fl!("password-mismatch");
                    None
                } else if user.full_name.is_empty()
                    || user.username.is_empty()
                    || !user_settings::valid_credential(&user.credential)
                    || !user_settings::valid_full_name(&user.full_name)
                    || user.credential_confirm.is_empty()
                {
                    validation_msg = fl!("users-password-credential-hint");
                    None
                } else {
                    Some(Message::NewUser(
                        user.username.clone(),
                        user.full_name.clone(),
                        user.credential.clone(),
                        user.is_admin,
                    ))
                };

                let add_user_button = widget::button::suggested(fl!("add-user"))
                    .on_press_maybe(complete_maybe)
                    .apply(Element::from);

                let cancel_button =
                    widget::button::standard(fl!("cancel")).on_press(Message::Dialog(None));

                widget::dialog()
                    .title(fl!("add-user"))
                    .control(
                        widget::ListColumn::default()
                            .add(full_name_input)
                            .add(username_input)
                            .add(credential_input)
                            .add(credential_confirm_input)
                            .add(text::body(fl!("users-password-credential-hint")))
                            .add(
                                row::with_capacity(3)
                                    .push(
                                        column::with_capacity(2)
                                            .push(text::body(crate::fl!("administrator")))
                                            .push(text::caption(crate::fl!(
                                                "administrator",
                                                "desc"
                                            )))
                                            .width(Length::Fill),
                                    )
                                    .push(horizontal().width(5.))
                                    .push(admin_toggler)
                                    .align_y(Alignment::Center),
                            ),
                    )
                    .primary_action(add_user_button)
                    .secondary_action(cancel_button)
                    .tertiary_action(widget::text::body(validation_msg))
                    .apply(Element::from)
            }

            Dialog::UpdatePassword(user) => {
                let credential_input = widget::container(
                    widget::text_input("", &user.credential)
                        .label(&self.credential_label)
                        .on_input(|value| {
                            Message::Dialog(Some(Dialog::UpdatePassword(User {
                                credential: value,
                                ..user.clone()
                            })))
                        }),
                );

                let credential_confirm_input = widget::container(
                    widget::text_input("", &user.credential_confirm)
                        .label(&self.credential_confirm_label)
                        .on_input(|value| {
                            Message::Dialog(Some(Dialog::UpdatePassword(User {
                                credential_confirm: value,
                                ..user.clone()
                            })))
                        }),
                );

                let mut validation_msg = String::new();
                let complete_maybe = if user.credential != user.credential_confirm
                    && !user.credential.is_empty()
                    && !user.credential_confirm.is_empty()
                {
                    validation_msg = fl!("password-mismatch");
                    None
                } else if !user_settings::valid_credential(&user.credential)
                    || user.credential_confirm.is_empty()
                {
                    validation_msg = fl!("users-password-credential-hint");
                    None
                } else {
                    Some(Message::SaveNewPassword(user.clone()))
                };

                let save_button = widget::button::suggested(fl!("save"))
                    .on_press_maybe(complete_maybe)
                    .apply(Element::from);

                let cancel_button =
                    widget::button::standard(fl!("cancel")).on_press(Message::Dialog(None));

                widget::dialog()
                    .title(fl!("change-password"))
                    .control(
                        widget::ListColumn::default()
                            .add(credential_input)
                            .add(credential_confirm_input)
                            .add(text::body(fl!("users-password-credential-hint"))),
                    )
                    .primary_action(save_button)
                    .secondary_action(cancel_button)
                    .tertiary_action(widget::text::body(validation_msg))
                    .apply(Element::from)
            }
        };

        dialog_element.map(crate::pages::Message::User).into()
    }

    fn on_enter(&mut self) -> cosmic::Task<crate::pages::Message> {
        if let Some(handle) = self.on_enter_handle.take() {
            handle.abort();
        }

        if self.pending.busy() {
            return cosmic::Task::none();
        }
        let Some(query) = self.next_query() else {
            return cosmic::Task::none();
        };
        let revision = self.pending.revision();
        let (task, handle) =
            cosmic::task::future(async move { Self::reload(query, revision).await }).abortable();
        self.on_enter_handle = Some(handle);
        task
    }

    fn on_leave(&mut self) -> cosmic::Task<crate::pages::Message> {
        if let Some(handle) = self.on_enter_handle.take() {
            handle.abort();
        }

        cosmic::Task::none()
    }
}

impl Page {
    pub async fn reload(query: u64, revision: (u64, bool)) -> Message {
        let result = user_settings::load().await.map(|accounts| {
            accounts
                .into_iter()
                .map(|account| User {
                    id: account.target.uid,
                    account_name: account.target.user.clone(),
                    username: account.target.user,
                    full_name: account.full_name,
                    is_admin: account.administrator,
                    profile_icon: (!account.icon_file.is_empty())
                        .then(|| icon::from_path(PathBuf::from(account.icon_file))),
                    ..User::default()
                })
                .collect()
        });
        Message::LoadPage(query, revision, result)
    }

    fn next_query(&mut self) -> Option<u64> {
        let Some(next) = self.query_generation.checked_add(1) else {
            self.notice = Some(
                Failure::Unavailable("restart Settings before refreshing again".into()).message(),
            );
            return None;
        };
        self.query_generation = next;
        Some(next)
    }

    fn target(&self, uid: u32) -> Option<Target> {
        self.users
            .iter()
            .find(|user| user.id == uid)
            .map(|user| Target {
                user: user.account_name.clone(),
                uid,
            })
    }

    fn start(&mut self, change: Change) -> cosmic::Task<crate::app::Message> {
        let generation = match self.pending.begin() {
            Ok(generation) => generation,
            Err(error) => {
                self.notice = Some(error.message());
                return cosmic::Task::none();
            }
        };
        self.last_outcome = None;
        self.notice = Some(fl!("regional-settings", "working"));
        cosmic::task::future(async move {
            Message::Finished(generation, user_settings::apply(change).await)
        })
    }

    pub fn update(&mut self, message: Message) -> cosmic::Task<crate::app::Message> {
        if self.pending.busy() && !matches!(&message, Message::Finished(..) | Message::LoadPage(..))
        {
            return cosmic::Task::none();
        }
        match message {
            Message::None => (),
            Message::Refresh => {
                let Some(query) = self.next_query() else {
                    return cosmic::Task::none();
                };
                let revision = self.pending.revision();
                return cosmic::task::future(async move { Self::reload(query, revision).await });
            }
            Message::LoadPage(query, revision, result) => {
                if query == self.query_generation
                    && revision == self.pending.revision()
                    && !self.pending.busy()
                {
                    match result {
                        Ok(users) => {
                            self.users = users;
                            self.selected_user_idx = None;
                        }
                        Err(error) => {
                            let detail = error.message();
                            let refresh = fl!("users-refresh-error", detail = detail.as_str());
                            self.notice = Some(match &self.last_outcome {
                                Some(outcome) => format!("{outcome}\n{refresh}"),
                                None => refresh,
                            });
                        }
                    }
                }
            }
            Message::Finished(generation, result) => {
                if self.pending.complete(generation) {
                    let outcome = crate::regional_settings::outcome(&result);
                    self.last_outcome = Some(outcome.clone());
                    self.notice = Some(outcome);
                    let Some(query) = self.next_query() else {
                        return cosmic::Task::none();
                    };
                    let revision = self.pending.revision();
                    return cosmic::task::future(
                        async move { Self::reload(query, revision).await },
                    );
                }
            }

            Message::SelectProfileImage(uid) => {
                return cosmic::task::future(async move {
                    let dialog_result = file_chooser::open::Dialog::new()
                        .title(fl!("users", "profile-add"))
                        .accept_label(fl!("dialog-add"))
                        .modal(false)
                        .open_file()
                        .await
                        .map(|response| response.url().to_owned());

                    Message::SelectedProfileImage(uid, Arc::new(dialog_result))
                });
            }

            Message::SelectedProfileImage(uid, image_result) => {
                let url = match image_result.as_ref() {
                    Ok(url) => url.clone(),
                    Err(why) => {
                        self.notice = Some(format!("{}: {why}", fl!("users-icon-requirement")));
                        return cosmic::Task::none();
                    }
                };
                let path = url
                    .to_file_path()
                    .ok()
                    .and_then(|path| path.to_str().map(str::to_owned));
                if let (Some(target), Some(path)) = (self.target(uid), path) {
                    return self.start(Change::Icon(target, path));
                }
                self.notice = Some(fl!("users-icon-requirement"));
            }

            Message::Edit(id, field, value) => {
                if let Some(user) = self.users.get_mut(id) {
                    match field {
                        EditorField::FullName => user.full_name = value,
                        EditorField::Username => user.username = value,
                    }
                }
            }

            Message::ToggleEdit(id, field) => {
                if let Some(user) = self.users.get_mut(id) {
                    match field {
                        EditorField::FullName => user.full_name_edit = !user.full_name_edit,
                        EditorField::Username => user.username_edit = !user.username_edit,
                    }
                }
            }

            Message::ApplyEdit(id, field) => {
                if let Some(user) = self.users.get_mut(id) {
                    let target = Target {
                        user: user.account_name.clone(),
                        uid: user.id,
                    };
                    let change = match field {
                        EditorField::FullName if user.full_name_edit => {
                            user.full_name_edit = false;
                            Some(Change::FullName(target, user.full_name.clone()))
                        }
                        EditorField::Username if user.username_edit => {
                            user.username_edit = false;
                            Some(Change::Rename(target, user.username.clone()))
                        }
                        _ => None,
                    };
                    if let Some(change) = change {
                        return self.start(change);
                    }
                }
            }

            Message::SaveNewPassword(user) => {
                self.dialog = None;
                if let Some(target) = self.target(user.id) {
                    return self.start(Change::Password(target, user.credential));
                }
            }

            Message::SelectUser(user_idx) => {
                match self.selected_user_idx {
                    Some(currently_selected_idx) if currently_selected_idx == user_idx => {
                        self.selected_user_idx = None;
                    }
                    _ => {
                        self.selected_user_idx = Some(user_idx);
                    }
                };
            }

            Message::SelectedUserDelete(uid) => {
                if let Some(target) = self.target(uid) {
                    return self.start(Change::Delete(target));
                }
            }

            Message::Dialog(dialog) => {
                self.dialog = dialog;
            }

            Message::NewUser(username, full_name, credential, is_admin) => {
                self.dialog = None;
                return self.start(Change::Create {
                    user: username,
                    full_name,
                    credential,
                    administrator: is_admin,
                });
            }

            Message::SelectedUserSetAdmin(uid, is_admin) => {
                if let Some(target) = self.target(uid) {
                    return self.start(Change::AccountType(target, is_admin));
                }
            }
        };

        cosmic::Task::none()
    }
}

impl page::AutoBind<crate::pages::Message> for Page {}

fn user_list() -> Section<crate::pages::Message> {
    crate::slab!(descriptions {
        user_type_standard = fl!("users", "standard");
        user_type_admin = fl!("users", "admin");
    });

    Section::default()
        .descriptions(descriptions)
        .view::<Page>(move |_binder, page, section| {
            let descriptions = &section.descriptions;
            let space_xxs = cosmic::theme::spacing().space_xxs;

            let users_list = page
                .users
                .iter()
                .enumerate()
                .map(|(idx, user)| {
                    let expanded =
                        matches!(page.selected_user_idx, Some(user_idx) if user_idx == idx);

                    let username =
                        widget::editable_input("", &user.username, user.username_edit, move |_| {
                            Message::ToggleEdit(idx, EditorField::Username)
                        })
                        .on_input(move |name| Message::Edit(idx, EditorField::Username, name))
                        .on_submit(move |_| Message::ApplyEdit(idx, EditorField::Username))
                        .on_unfocus(Message::ApplyEdit(idx, EditorField::Username));

                    let password = widget::button::standard(fl!("change-password"))
                        .on_press(Message::Dialog(Some(Dialog::UpdatePassword(user.clone()))))
                        .apply(Element::from);

                    let fullname = widget::editable_input(
                        "",
                        &user.full_name,
                        user.full_name_edit,
                        move |_| Message::ToggleEdit(idx, EditorField::FullName),
                    )
                    .on_input(move |name| Message::Edit(idx, EditorField::FullName, name))
                    .on_submit(move |_| Message::ApplyEdit(idx, EditorField::FullName))
                    .on_unfocus(Message::ApplyEdit(idx, EditorField::FullName));

                    let fullname_text = text::body(if !user.full_name.is_empty() {
                        &user.full_name
                    } else {
                        &user.username
                    });

                    let account_type = text::caption(if user.is_admin {
                        &descriptions[user_type_admin]
                    } else {
                        &descriptions[user_type_standard]
                    });

                    let profile_icon_handle = user
                        .profile_icon
                        .clone()
                        .unwrap_or_else(|| page.default_icon.clone());

                    let profile_icon = widget::button::icon(profile_icon_handle)
                        .large()
                        .padding(0)
                        .class(cosmic::theme::Button::Standard)
                        .on_press(Message::SelectProfileImage(user.id));

                    let account_details_content = settings::item_row(vec![
                        widget::row::with_capacity(2)
                            .push(profile_icon)
                            .push(
                                column::with_capacity(2)
                                    .push(fullname_text)
                                    .push(account_type),
                            )
                            .align_y(Alignment::Center)
                            .spacing(space_xxs)
                            .width(Length::Fill)
                            .into(),
                        icon::from_name(if expanded {
                            "go-up-symbolic"
                        } else {
                            "go-down-symbolic"
                        })
                        .icon()
                        .size(16)
                        .into(),
                    ]);

                    let mut user_list = crate::widget::claw_list_column().add(
                        list::button(account_details_content)
                            .selected(expanded)
                            .on_press(Message::SelectUser(idx)),
                    );

                    if expanded {
                        user_list = user_list
                            .add(settings::item(&page.fullname_label, fullname))
                            .add(settings::item(&page.username_label, username))
                            .add(settings::item(&page.password_label, password))
                            .add(settings::item_row(vec![
                                column::with_capacity(2)
                                    .push(text::body(crate::fl!("administrator")))
                                    .push(text::caption(crate::fl!("administrator", "desc")))
                                    .width(Length::Fill)
                                    .into(),
                                horizontal().width(5.).into(),
                                widget::toggler(user.is_admin)
                                    .on_toggle(|enabled| {
                                        Message::SelectedUserSetAdmin(user.id, enabled)
                                    })
                                    .into(),
                            ]));

                        if page.users.len() > 1 {
                            user_list = user_list.add(settings::item_row(vec![
                                horizontal().width(Length::Fill).into(),
                                widget::button::destructive(crate::fl!("remove-user"))
                                    .on_press(Message::SelectedUserDelete(user.id))
                                    .into(),
                            ]));
                        }
                    }

                    Element::from(user_list)
                })
                .fold(
                    widget::column::with_capacity(page.users.len()),
                    |col, user| col.push(user),
                )
                .spacing(space_xxs)
                .width(Length::Fill);

            let add_user = widget::button::standard(crate::fl!("add-user"))
                .on_press(Message::Dialog(Some(Dialog::AddNewUser(User::default()))))
                .apply(widget::container)
                .width(Length::Fill)
                .align_x(Alignment::End);

            let refresh =
                widget::button::standard(fl!("app-permissions-refresh")).on_press(Message::Refresh);
            let notice = page.notice.clone().unwrap_or_default();
            widget::column::with_capacity(4)
                .push(text::body(notice))
                .push(users_list)
                .push(refresh)
                .push(add_user)
                .spacing(space_xxs)
                .apply(Element::from)
                .map(crate::pages::Message::User)
        })
}
