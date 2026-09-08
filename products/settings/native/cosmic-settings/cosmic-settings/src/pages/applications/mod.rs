// Copyright 2023 System76 <info@system76.com>
// SPDX-License-Identifier: GPL-3.0-only

#[cfg(feature = "page-default-apps")]
pub mod default_apps;

pub mod startup_apps;
mod permissions;

#[cfg(feature = "page-legacy-applications")]
pub mod legacy_applications;

use cosmic_settings_page as page;

#[derive(Default)]
pub struct Page {
    entity: page::Entity,
    permissions: permissions::State,
}

impl page::Page<crate::pages::Message> for Page {
    fn set_id(&mut self, entity: page::Entity) {
        self.entity = entity;
    }

    fn info(&self) -> page::Info {
        page::Info::new("applications", "preferences-applications-symbolic")
            .title(fl!("applications"))
    }

    fn content(&self, sections: &mut slotmap::SlotMap<page::section::Entity, page::Section<crate::pages::Message>>) -> Option<page::Content> {
        Some(vec![sections.insert(page::Section::default()
            .title(fl!("app-permissions"))
            .view::<Self>(|_, page, _| page.permissions.view().map(crate::pages::Message::Applications)))])
    }

    fn on_enter(&mut self) -> cosmic::Task<crate::pages::Message> {
        self.permissions.update(Message::Refresh).map(crate::pages::Message::Applications)
    }

    fn on_leave(&mut self) -> cosmic::Task<crate::pages::Message> {
        self.permissions.cancel();
        cosmic::Task::none()
    }
}

impl page::AutoBind<crate::pages::Message> for Page {
    fn sub_pages(
        mut page: page::Insert<crate::pages::Message>,
    ) -> page::Insert<crate::pages::Message> {
        #[cfg(feature = "page-default-apps")]
        {
            page = page.sub_page::<default_apps::Page>();
        }

        page = page.sub_page::<startup_apps::Page>();

        #[cfg(feature = "page-legacy-applications")]
        {
            page = page.sub_page::<legacy_applications::Page>();
        }

        page
    }
}

pub use permissions::Message;

impl Page {
    pub fn update(&mut self, message: Message) -> cosmic::Task<crate::Message> {
        self.permissions.update(message).map(crate::pages::Message::Applications).map(Into::into)
    }
}
