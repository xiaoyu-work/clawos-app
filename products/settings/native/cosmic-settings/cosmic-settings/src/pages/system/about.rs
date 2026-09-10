// Copyright 2023 System76 <info@system76.com>
// SPDX-License-Identifier: GPL-3.0-only

use cosmic::iced::Alignment;
use cosmic_settings_page::{self as page, Section, section};

use super::info::Info;
use crate::regional_settings::{self, Change, Failure, Pending};
use cosmic::widget::{editable_input, list_column, settings, text};
use cosmic::{Apply, Task};
use slotmap::SlotMap;

#[derive(Clone, Debug)]
pub enum Message {
    HostnameEdit(bool),
    HostnameInput(String),
    HostnameSubmit,
    HostnameFinished(u64, String, Result<(), Failure>),
    Info((u64, bool), Box<Info>),
}

impl From<Message> for crate::app::Message {
    fn from(message: Message) -> Self {
        crate::pages::Message::About(message).into()
    }
}

impl From<Message> for crate::pages::Message {
    fn from(message: Message) -> Self {
        crate::pages::Message::About(message)
    }
}

#[derive(Clone, Debug, Default)]
pub struct Page {
    entity: page::Entity,
    editing_device_name: bool,
    hostname_input: String,
    info: Info,
    on_enter_handle: Option<cosmic::iced::task::Handle>,
    pending: Pending,
    notice: Option<String>,
}

impl page::AutoBind<crate::pages::Message> for Page {}

impl page::Page<crate::pages::Message> for Page {
    fn set_id(&mut self, entity: page::Entity) {
        self.entity = entity;
    }

    fn content(
        &self,
        sections: &mut SlotMap<section::Entity, Section<crate::pages::Message>>,
    ) -> Option<page::Content> {
        Some(vec![
            sections.insert(device()),
            sections.insert(hardware()),
            sections.insert(os()),
        ])
    }

    fn info(&self) -> page::Info {
        page::Info::new("about", "help-about-symbolic")
            .title(fl!("about"))
            .description(fl!("xdg-entry-about-comment"))
    }

    fn on_enter(&mut self) -> Task<crate::pages::Message> {
        let revision = self.pending.revision();
        let (task, handle) = Task::future(async move {
            let info = Info::load().await;
            crate::pages::Message::About(Message::Info(revision, Box::new(info)))
        })
        .abortable();

        self.on_enter_handle = Some(handle);
        task
    }

    fn on_leave(&mut self) -> Task<crate::pages::Message> {
        if let Some(handle) = self.on_enter_handle.take() {
            handle.abort();
        }

        Task::none()
    }
}

impl Page {
    pub fn update(&mut self, message: Message) -> cosmic::app::Task<crate::Message> {
        match message {
            Message::HostnameEdit(editing) => {
                if !self.pending.busy() {
                    self.editing_device_name = editing;
                }
            }

            Message::HostnameInput(hostname) => {
                if !self.pending.busy() {
                    self.hostname_input = hostname;
                }
            }

            Message::HostnameSubmit => return self.hostname_submit(),

            Message::Info(revision, info) if revision == self.pending.revision() => {
                let replace_input = !self.pending.busy()
                    && !self.editing_device_name
                    && self.hostname_input == self.info.device_name;
                self.info = *info;
                if replace_input {
                    self.hostname_input = self.info.device_name.clone();
                }
            }

            Message::HostnameFinished(generation, name, result)
                if self.pending.complete(generation) =>
            {
                if result.is_ok() {
                    self.info.device_name = name;
                    self.editing_device_name = false;
                } else {
                    self.editing_device_name = true;
                }
                self.notice = Some(regional_settings::outcome(&result));
            }
            Message::Info(..) | Message::HostnameFinished(..) => {}
        }

        Task::none()
    }

    fn hostname_submit(&mut self) -> cosmic::app::Task<crate::app::Message> {
        if self.pending.busy() || self.hostname_input == self.info.device_name {
            return Task::none();
        }

        if self.hostname_input.len() > 64
            || !self.hostname_input.is_ascii()
            || self.hostname_input.ends_with('.')
            || !hostname_validator::is_valid(&self.hostname_input)
        {
            self.notice = Some(fl!("regional-settings", "invalid-hostname"));
            self.editing_device_name = true;
            return Task::none();
        }

        let generation = match self.pending.begin() {
            Ok(generation) => generation,
            Err(error) => {
                self.notice = Some(error.message());
                return Task::none();
            }
        };
        self.notice = Some(fl!("regional-settings", "working"));
        self.editing_device_name = false;
        let hostname = self.hostname_input.clone();

        cosmic::Task::future(async move {
            let result = regional_settings::call(Change::StaticHostname {
                hostname: hostname.clone(),
            })
            .await;
            Message::HostnameFinished(generation, hostname, result)
        })
        .map(crate::app::Message::from)
        .map(Into::into)
    }
}

fn device() -> Section<crate::pages::Message> {
    crate::slab!(descriptions {
        device = fl!("about-device");
        device_desc = fl!("about-device", "desc");
    });

    Section::default()
        .descriptions(descriptions)
        .view::<Page>(move |_binder, page, section| {
            let desc = &section.descriptions;

            let hostname_input: cosmic::Element<'_, Message> = if page.pending.busy() {
                text::body(&page.hostname_input).into()
            } else {
                editable_input(
                    "",
                    &page.hostname_input,
                    page.editing_device_name,
                    Message::HostnameEdit,
                )
                .width(250.)
                .on_input(Message::HostnameInput)
                .on_unfocus(Message::HostnameSubmit)
                .on_submit(|_| Message::HostnameSubmit)
                .into()
            };

            let device_name = settings::item::builder(&*desc[device])
                .description(&*desc[device_desc])
                .flex_control(hostname_input);

            let mut content = crate::widget::claw_list_column().add(device_name);
            if let Some(notice) = &page.notice {
                content = content.add(text::body(notice));
            }
            content
                .apply(cosmic::Element::from)
                .map(crate::pages::Message::About)
        })
}

#[cfg(test)]
mod tests {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/unit/pages/system/about.rs"
    ));
}

fn hardware() -> Section<crate::pages::Message> {
    crate::slab!(descriptions {
        model = fl!("about-hardware", "model");
        memory = fl!("about-hardware", "memory");
        processor = fl!("about-hardware", "processor");
        graphics = fl!("about-hardware", "graphics");
        disk_capacity = fl!("about-hardware", "disk-capacity");
    });

    Section::default()
        .title(fl!("about-hardware"))
        .descriptions(descriptions)
        .view::<Page>(move |_binder, page, section| {
            let desc = &section.descriptions;

            let mut section_builder = crate::widget::claw_section()
                .title(&section.title)
                .add(
                    settings::flex_item(&*desc[model], text::body(&page.info.hardware_model))
                        .align_items(Alignment::Center),
                )
                .add(
                    settings::flex_item(&*desc[memory], text::body(&page.info.memory))
                        .align_items(Alignment::Center),
                )
                .add(
                    settings::flex_item(&*desc[processor], text::body(&page.info.processor))
                        .align_items(Alignment::Center),
                );

            for card in &page.info.graphics {
                section_builder = section_builder.add(
                    settings::flex_item(&*desc[graphics], text::body(card.as_str()))
                        .align_items(Alignment::Center),
                );
            }

            section_builder
                .add(
                    settings::flex_item(
                        &*desc[disk_capacity],
                        text::body(&page.info.disk_capacity),
                    )
                    .align_items(Alignment::Center),
                )
                .into()
        })
}

fn os() -> Section<crate::pages::Message> {
    crate::slab!(descriptions {
        os = fl!("about-os", "os");
        os_arch = fl!("about-os", "os-architecture");
        kernel = fl!("about-os", "kernel");
        desktop = fl!("about-os", "desktop-environment");
        windowing_system = fl!("about-os", "windowing-system");
    });

    Section::default()
        .title(fl!("about-os"))
        .descriptions(descriptions)
        .view::<Page>(move |_binder, page, section| {
            let desc = &section.descriptions;
            crate::widget::claw_section()
                .title(&section.title)
                .add(
                    settings::flex_item(&*desc[os], text::body(&page.info.operating_system))
                        .align_items(Alignment::Center),
                )
                .add(
                    settings::flex_item(&*desc[os_arch], text::body(&page.info.os_architecture))
                        .align_items(Alignment::Center),
                )
                .add(
                    settings::flex_item(&*desc[kernel], text::body(&page.info.kernel_version))
                        .align_items(Alignment::Center),
                )
                .add(
                    settings::flex_item(
                        &*desc[desktop],
                        text::body(&page.info.desktop_environment),
                    )
                    .align_items(Alignment::Center),
                )
                .add(
                    settings::flex_item(
                        &*desc[windowing_system],
                        text::body(&page.info.windowing_system),
                    )
                    .align_items(Alignment::Center),
                )
                .into()
        })
}

// Related settings: for 2nd COSMIC release
// fn related() -> Section<crate::pages::Message> {
//     Section::default()
//         .title(fl!("about-related"))
//         .descriptions(vec![fl!("about-related", "support").into()])
//         .view::<Page>(move |_binder, _page, section| {
//             settings::section().title(&section.title)
//                 .add(settings::item(&*section.descriptions[0], text::body("TODO")))
//                 .into()
//         })
// }

// fn page(app: &crate::SettingsApp) -> &Page {
//     app.pages
//         .resource::<Page>()
//         .expect("missing system->about page")
// }
