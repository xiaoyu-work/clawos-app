// Copyright 2023 System76 <info@system76.com>
// SPDX-License-Identifier: GPL-3.0-only

use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

use crate::regional_settings::{self, Change, Failure, Pending};
use crate::widget::selection_context_item;
use cosmic::app::{ContextDrawer, context_drawer};
use cosmic::iced::{Alignment, Length};
use cosmic::widget::{self, button};
use cosmic::{Apply, Element};
use cosmic_config::{ConfigGet, ConfigSet};
use cosmic_settings_page::Section;
use cosmic_settings_page::{self as page, section};
use eyre::Context;
use icu::{
    calendar::{types::Weekday, week},
    datetime::{
        DateTimeFormatter, DateTimeFormatterPreferences, fieldsets,
        input::{Date, DateTime, Time},
    },
    decimal::{DecimalFormatter, input::Decimal},
    locale::Locale,
};
use locales_rs as locale;
use regex::Regex;
use slotmap::{DefaultKey, SlotMap};

static GNOME_LANGUAGE_SELECTOR: &str = "gnome-language-selector";

#[derive(Clone, Debug)]
pub enum Message {
    AddLanguage(DefaultKey),
    AddLanguageContext,
    AddLanguageSearch(String),
    ExpandLanguagePopover(Option<usize>),
    InstallAdditionalLanguages,
    SelectRegion(DefaultKey),
    SourceContext(SourceContext),
    Refresh((u64, bool), Arc<eyre::Result<PageRefresh>>),
    Changed(Box<ChangeResult>),
    RegionContext,
    RemoveLanguage(DefaultKey),
}

impl From<Message> for crate::app::Message {
    fn from(message: Message) -> Self {
        crate::pages::Message::Region(message).into()
    }
}

impl From<Message> for crate::pages::Message {
    fn from(message: Message) -> Self {
        crate::pages::Message::Region(message)
    }
}

enum ContextView {
    AddLanguage,
    Region,
}

#[derive(Clone, Debug)]
pub enum SourceContext {
    MoveDown(usize),
    MoveUp(usize),
    Remove(usize),
}

#[derive(Clone, Debug)]
pub struct SystemLocale {
    lang_code: String,
    display_name: String,
    region_name: String,
}

impl Eq for SystemLocale {}

impl Ord for SystemLocale {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.display_name.cmp(&other.display_name)
    }
}

impl PartialOrd for SystemLocale {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl PartialEq for SystemLocale {
    fn eq(&self, other: &Self) -> bool {
        self.display_name == other.display_name
    }
}

#[derive(Debug)]
pub struct PageRefresh {
    config: Option<(cosmic_config::Config, Vec<String>)>,
    registry: Registry,
    language: Option<SystemLocale>,
    region: Option<SystemLocale>,
    available_languages: SlotMap<DefaultKey, SystemLocale>,
    system_locales: BTreeMap<String, SystemLocale>,
    language_selector_available: bool,
}

#[derive(Clone, Debug)]
pub struct ChangeResult {
    generation: u64,
    language: SystemLocale,
    region: SystemLocale,
    system: Result<(), Failure>,
    owner: Option<Result<(), Failure>>,
    time_preferences: Option<Result<(), String>>,
}

#[derive(Default)]
pub struct Page {
    entity: page::Entity,
    config: Option<(cosmic_config::Config, Vec<String>)>,
    context: Option<ContextView>,
    language: Option<SystemLocale>,
    region: Option<SystemLocale>,
    available_languages: SlotMap<DefaultKey, SystemLocale>,
    system_locales: BTreeMap<String, SystemLocale>,
    registry: Option<locale::Registry>,
    expanded_source_popover: Option<usize>,
    add_language_search: String,
    /// Whether gnome-language-selector is in the path.
    language_selector_available: bool,
    /// Cached LC_NUMERIC locale in icu locale format.
    numeric_locale: Option<Locale>,
    /// Cached LC_TIME locale in icu locale format.
    time_locale: Option<Locale>,
    pending: Pending,
    notice: Option<String>,
}

impl page::Page<crate::pages::Message> for Page {
    fn set_id(&mut self, entity: page::Entity) {
        self.entity = entity;
    }

    fn content(
        &self,
        sections: &mut SlotMap<section::Entity, Section<crate::pages::Message>>,
    ) -> Option<page::Content> {
        Some(vec![
            sections.insert(preferred_languages::section()),
            sections.insert(formatting::section()),
        ])
    }

    fn info(&self) -> page::Info {
        page::Info::new("time-region", "preferences-region-and-language-symbolic")
            .title(fl!("time-region"))
            .description(fl!("xdg-entry-region-language-comment"))
    }

    fn on_enter(&mut self) -> cosmic::Task<crate::pages::Message> {
        let revision = self.pending.revision();
        cosmic::task::future(
            async move { Message::Refresh(revision, Arc::new(page_reload().await)) },
        )
    }

    fn on_leave(&mut self) -> cosmic::Task<crate::pages::Message> {
        self.add_language_search = String::new();
        self.available_languages = SlotMap::new();
        self.config = None;
        self.context = None;
        self.expanded_source_popover = None;
        self.language = None;
        self.region = None;
        self.registry = None;
        self.system_locales = BTreeMap::new();
        cosmic::Task::none()
    }

    fn context_drawer(&self) -> Option<ContextDrawer<'_, crate::pages::Message>> {
        Some(match self.context.as_ref()? {
            ContextView::AddLanguage => {
                let search = widget::search_input("", &self.add_language_search)
                    .on_input(Message::AddLanguageSearch)
                    .on_clear(Message::AddLanguageSearch(String::new()))
                    .apply(Element::from)
                    .map(crate::pages::Message::from);
                let drawer = context_drawer(
                    self.add_language_view().map(crate::pages::Message::from),
                    crate::pages::Message::CloseContextDrawer,
                )
                .title(fl!("add-language", "context"))
                .header(search);

                if self.language_selector_available {
                    let install_additional_button =
                        widget::button::standard(fl!("install-additional-languages"))
                            .on_press(Message::InstallAdditionalLanguages)
                            .apply(widget::container)
                            .width(Length::Fill)
                            .align_x(Alignment::End)
                            .apply(Element::from)
                            .map(crate::pages::Message::from);

                    drawer.footer(install_additional_button)
                } else {
                    drawer
                }
            }
            ContextView::Region => {
                let search = widget::search_input("", &self.add_language_search)
                    .on_input(Message::AddLanguageSearch)
                    .on_clear(Message::AddLanguageSearch(String::new()))
                    .apply(Element::from)
                    .map(crate::pages::Message::from);

                context_drawer(
                    self.region_view().map(crate::pages::Message::from),
                    crate::pages::Message::CloseContextDrawer,
                )
                .title(fl!("region"))
                .header(search)
            }
        })
    }
}

impl Page {
    pub fn update(&mut self, message: Message) -> cosmic::Task<crate::app::Message> {
        if self.pending.busy()
            && matches!(
                &message,
                Message::AddLanguage(_)
                    | Message::RemoveLanguage(_)
                    | Message::SourceContext(_)
                    | Message::SelectRegion(_)
                    | Message::ExpandLanguagePopover(_)
                    | Message::InstallAdditionalLanguages
            )
        {
            return cosmic::Task::none();
        }
        match message {
            Message::AddLanguage(id) => {
                if let Some(language) = self.available_languages.get(id)
                    && let Some((config, locales)) = self.config.as_mut()
                    && !locales.contains(&language.lang_code)
                {
                    let mut next = locales.clone();
                    next.push(language.lang_code.clone());
                    match config.set("system_locales", &next) {
                        Ok(()) => *locales = next,
                        Err(error) => {
                            self.notice = Some(fl!(
                                "regional-settings",
                                "local-error",
                                detail = error.to_string()
                            ))
                        }
                    }
                }
            }

            Message::RemoveLanguage(id) => {
                if let Some(language) = self.available_languages.remove(id)
                    && let Some((config, locales)) = self.config.as_mut()
                    && let Some(pos) = locales.iter().position(|l| l == &language.lang_code)
                {
                    let mut next = locales.clone();
                    next.remove(pos);
                    match config.set("system_locales", &next) {
                        Ok(()) => *locales = next,
                        Err(error) => {
                            self.notice = Some(fl!(
                                "regional-settings",
                                "local-error",
                                detail = error.to_string()
                            ))
                        }
                    }
                }
            }

            Message::SelectRegion(id) => {
                if let Some((region, language)) =
                    self.available_languages.get(id).zip(self.language.as_ref())
                {
                    return self.change(language.clone(), region.clone(), None, true);
                }
            }

            Message::AddLanguageContext => {
                self.context = Some(ContextView::AddLanguage);
                return cosmic::Task::done(crate::app::Message::OpenContextDrawer(self.entity));
            }

            Message::AddLanguageSearch(search) => {
                self.add_language_search = search;
            }

            Message::ExpandLanguagePopover(id) => {
                self.expanded_source_popover = id;
            }

            Message::InstallAdditionalLanguages => {
                let revision = self.pending.revision();
                return cosmic::task::future(async move {
                    _ = tokio::task::spawn_blocking(|| {
                        crate::claw_glue::start(&[GNOME_LANGUAGE_SELECTOR])
                    })
                    .await;

                    Message::Refresh(revision, Arc::new(page_reload().await))
                });
            }

            Message::Refresh(revision, result) => {
                if revision != self.pending.revision() {
                    return cosmic::Task::none();
                }
                let Some(result) = Arc::into_inner(result) else {
                    self.notice = Some(fl!(
                        "regional-settings",
                        "refresh-error",
                        detail = "refresh result was shared; refresh again"
                    ));
                    return cosmic::Task::none();
                };
                match result {
                    Ok(page_refresh) => {
                        self.config = page_refresh.config;
                        self.available_languages = page_refresh.available_languages;
                        self.system_locales = page_refresh.system_locales;
                        self.language = page_refresh.language;
                        self.region = page_refresh.region;
                        self.registry = Some(page_refresh.registry.0);
                        self.language_selector_available = page_refresh.language_selector_available;
                        self.numeric_locale = self.icu_locale_from_env("LC_NUMERIC");
                        self.time_locale = self.icu_locale_from_env("LC_TIME");
                    }

                    Err(why) => {
                        tracing::error!(?why, "failed to get locales from the system");
                        let message = fl!(
                            "regional-settings",
                            "refresh-error",
                            detail = why.to_string()
                        );
                        self.notice = Some(match self.notice.take() {
                            Some(previous) => format!("{previous}\n{message}"),
                            None => message,
                        });
                    }
                }
            }

            Message::Changed(result) => {
                if !self.pending.complete(result.generation) {
                    return cosmic::Task::none();
                }
                if result.system.is_ok() {
                    self.numeric_locale = parse_locale(&result.region.lang_code);
                    self.time_locale = self.numeric_locale.clone();
                    self.language = Some(result.language);
                    self.region = Some(result.region);
                }
                let mut notice = match &result.owner {
                    Some(owner) => fl!(
                        "regional-settings",
                        "partial",
                        system = regional_settings::outcome(&result.system),
                        owner = regional_settings::outcome(owner)
                    ),
                    None => regional_settings::outcome(&result.system),
                };
                if let Some(Err(error)) = result.time_preferences {
                    notice.push('\n');
                    notice.push_str(&fl!("regional-settings", "local-error", detail = error));
                }
                self.notice = Some(notice);
                let revision = self.pending.revision();
                return cosmic::task::future(async move {
                    Message::Refresh(revision, Arc::new(page_reload().await))
                });
            }

            Message::RegionContext => {
                self.context = Some(ContextView::Region);
                return cosmic::Task::done(crate::app::Message::OpenContextDrawer(self.entity));
            }

            Message::SourceContext(context_message) => {
                self.expanded_source_popover = None;

                if let Some((config, locales)) = self.config.as_mut() {
                    let mut next = locales.clone();
                    match context_message {
                        SourceContext::MoveDown(id) => {
                            if id < next.len().saturating_sub(1) {
                                next.swap(id, id + 1);
                            } else {
                                return cosmic::Task::none();
                            }
                        }

                        SourceContext::MoveUp(id) => {
                            if id > 0 && id < next.len() {
                                next.swap(id, id - 1);
                            } else {
                                return cosmic::Task::none();
                            }
                        }

                        SourceContext::Remove(id) => {
                            if id >= next.len() {
                                return cosmic::Task::none();
                            }
                            next.remove(id);
                        }
                    }

                    if let Err(error) = config.set("system_locales", &next) {
                        self.notice = Some(fl!(
                            "regional-settings",
                            "local-error",
                            detail = error.to_string()
                        ));
                        return cosmic::Task::none();
                    }
                    *locales = next;
                    let language_list = build_language_list(locales);

                    if let Some(language_code) = locales.first()
                        && let Some(language) = self
                            .available_languages
                            .values()
                            .find(|lang| &lang.lang_code == language_code)
                    {
                        let language = language.clone();
                        let region = self.region.clone().unwrap_or_else(|| language.clone());
                        return self.change(language, region, Some(language_list), false);
                    }
                    self.notice = Some(fl!("regional-settings", "local-only"));
                }
            }
        }

        cosmic::Task::none()
    }

    fn change(
        &mut self,
        language: SystemLocale,
        region: SystemLocale,
        languages: Option<String>,
        update_time: bool,
    ) -> cosmic::Task<crate::app::Message> {
        let generation = match self.pending.begin() {
            Ok(generation) => generation,
            Err(error) => {
                self.notice = Some(error.message());
                return cosmic::Task::none();
            }
        };
        self.expanded_source_popover = None;
        self.notice = Some(fl!("regional-settings", "working"));
        cosmic::task::future(async move {
            let system = regional_settings::call(Change::SystemLocale {
                lang: language.lang_code.clone(),
                region: region.lang_code.clone(),
            })
            .await;
            let time_preferences = if update_time && system.is_ok() {
                Some(update_time_settings_after_region_change(&region.lang_code))
            } else {
                None
            };
            // The owner's preference is independent of the system default.
            let owner = match languages {
                Some(languages) => {
                    Some(regional_settings::call(Change::OwnerLanguage { languages }).await)
                }
                None => None,
            };
            Message::Changed(Box::new(ChangeResult {
                generation,
                language,
                region,
                system,
                owner,
                time_preferences,
            }))
        })
    }

    fn add_language_view(&self) -> cosmic::Element<'_, crate::pages::Message> {
        let mut list = widget::list_column::with_capacity(self.available_languages.len());
        let search_input = &self.add_language_search.trim().to_lowercase();

        for (id, available_language) in &self.available_languages {
            if search_input.is_empty()
                || available_language
                    .display_name
                    .to_lowercase()
                    .contains(search_input)
            {
                let is_installed = self
                    .config
                    .as_ref()
                    .is_some_and(|(_, locales)| locales.contains(&available_language.lang_code));

                list = list.add(selection_context_item(
                    &available_language.display_name,
                    is_installed,
                    if is_installed {
                        Message::RemoveLanguage(id)
                    } else {
                        Message::AddLanguage(id)
                    },
                ))
            }
        }

        list.apply(Element::from).map(crate::pages::Message::Region)
    }

    fn icu_locale_from_env(&self, key: &'static str) -> Option<Locale> {
        self.system_locales
            .get(key)
            .or_else(|| self.system_locales.get("LANG"))
            .map_or("en-US", |locale| &locale.lang_code)
            .split('.')
            .next()
            .unwrap_or("en-US")
            .replacen('_', "-", 1)
            .parse::<Locale>()
            .ok()
    }

    fn formatted_date(&self) -> String {
        let Some(locale) = self.time_locale.as_ref() else {
            return String::new();
        };

        let prefs = DateTimeFormatterPreferences::from(locale);
        let dtf = DateTimeFormatter::try_new(prefs, fieldsets::YMD::medium()).unwrap();

        let datetime = DateTime {
            date: Date::try_new_gregorian(1776, 7, 4).unwrap(),
            time: Time::try_new(12, 0, 0, 0).unwrap(),
        };

        dtf.format(&datetime).to_string()
    }

    fn formatted_dates_and_times(&self) -> String {
        let Some(locale) = self.time_locale.as_ref() else {
            return String::new();
        };

        let prefs = DateTimeFormatterPreferences::from(locale);
        let dtf = DateTimeFormatter::try_new(prefs, fieldsets::YMDT::long()).unwrap();

        let datetime = DateTime {
            date: Date::try_new_gregorian(1776, 7, 4).unwrap(),
            time: Time::try_new(13, 0, 0, 0).unwrap(),
        };

        dtf.format(&datetime).to_string()
    }

    fn formatted_time(&self) -> String {
        let Some(locale) = self.time_locale.as_ref() else {
            return String::new();
        };

        let prefs = DateTimeFormatterPreferences::from(locale);
        let dtf = DateTimeFormatter::try_new(prefs, fieldsets::T::medium()).unwrap();

        let datetime = DateTime {
            date: Date::try_new_gregorian(1776, 7, 4).unwrap(),
            time: Time::try_new(13, 0, 0, 0).unwrap(),
        };

        dtf.format(&datetime).to_string()
    }

    fn formatted_numbers(&self) -> String {
        let Some(locale) = self.numeric_locale.as_ref() else {
            return String::new();
        };

        let formatter = DecimalFormatter::try_new(locale.into(), Default::default()).unwrap();
        let mut value = Decimal::from(123456789);
        value.multiply_pow10(-2);

        formatter.format(&value).to_string()
    }

    fn region_view(&self) -> cosmic::Element<'_, crate::pages::Message> {
        let mut list = widget::list_column::with_capacity(self.available_languages.len());
        if let Some(notice) = &self.notice {
            list = list.add(widget::text::body(notice));
        }

        let search_input = &self.add_language_search.trim().to_lowercase();

        for (id, locale) in &self.available_languages {
            if search_input.is_empty() || locale.display_name.to_lowercase().contains(search_input)
            {
                let is_selected = self
                    .region
                    .as_ref()
                    .is_some_and(|l| l.lang_code == locale.lang_code);

                list = list.add(selection_context_item(
                    &locale.region_name,
                    is_selected,
                    if is_selected || self.pending.busy() {
                        None
                    } else {
                        Some(Message::SelectRegion(id))
                    },
                ))
            }
        }

        list.apply(Element::from).map(crate::pages::Message::Region)
    }
}

impl page::AutoBind<crate::pages::Message> for Page {}

mod preferred_languages {
    use crate::pages::time::region::localized_iso_codes;

    use super::Message;
    use cosmic::{
        Apply,
        iced::{Alignment, Length},
        widget,
    };
    use cosmic_settings_page::Section;

    pub fn section() -> Section<crate::pages::Message> {
        crate::slab!(descriptions {
            pref_lang_desc = fl!("preferred-languages", "desc");
            add_lang_txt = fl!("add-language");
        });

        Section::default()
            .title(fl!("preferred-languages"))
            .descriptions(descriptions)
            .view::<super::Page>(move |_binder, page, section| {
                let title = widget::text::body(&section.title).font(cosmic::font::bold());

                let description = widget::text::body(&section.descriptions[pref_lang_desc]);

                let mut content = crate::widget::claw_section();

                if let Some(((_config, locales), registry)) =
                    page.config.as_ref().zip(page.registry.as_ref())
                {
                    for (id, locale) in locales.iter().enumerate() {
                        if let Some(locale) = registry.locale(locale) {
                            let (language, country) = localized_iso_codes(&locale);

                            content = content.add(super::language_element(
                                id,
                                format!("{} ({})", language, country),
                                page.expanded_source_popover,
                                !page.pending.busy(),
                            ));
                        }
                    }
                }

                let add_language_button =
                    widget::button::standard(&section.descriptions[add_lang_txt])
                        .on_press_maybe(
                            (!page.pending.busy()).then_some(Message::AddLanguageContext),
                        )
                        .apply(widget::container)
                        .width(Length::Fill)
                        .align_x(Alignment::End);

                let mut view = widget::column::with_capacity(6)
                    .push(title)
                    .push(description)
                    .push(content)
                    .push(add_language_button);
                if let Some(notice) = &page.notice {
                    view = view.push(widget::text::body(notice));
                }
                view.spacing(cosmic::theme::spacing().space_xxs)
                    .apply(cosmic::Element::from)
                    .map(Into::into)
            })
    }
}

mod formatting {
    use super::Message;
    use cosmic::{Apply, widget};
    use cosmic_settings_page::Section;

    pub fn section() -> Section<crate::pages::Message> {
        crate::slab!(descriptions {
            formatting_txt = fl!("formatting");
            dates_txt = [&fl!("formatting", "dates"), ":"].concat();
            time_txt = [&fl!("formatting", "time"), ":"].concat();
            date_and_time_txt = [&fl!("formatting", "date-and-time"), ":"].concat();
            numbers_txt = [&fl!("formatting", "numbers"), ":"].concat();
            region_txt = fl!("region");
        });

        Section::default()
            .title(fl!("formatting"))
            .descriptions(descriptions)
            .view::<super::Page>(move |_binder, page, section| {
                let desc = &section.descriptions;

                let dates = widget::row::with_capacity(2)
                    .push(widget::text::body(&desc[dates_txt]))
                    .push(widget::text::body(page.formatted_date()).font(cosmic::font::bold()))
                    .spacing(4);

                let time = widget::row::with_capacity(2)
                    .push(widget::text::body(&desc[time_txt]))
                    .push(widget::text::body(page.formatted_time()).font(cosmic::font::bold()))
                    .spacing(4);

                let dates_and_times = widget::row::with_capacity(2)
                    .push(widget::text::body(&desc[date_and_time_txt]))
                    .push(
                        widget::text::body(page.formatted_dates_and_times())
                            .font(cosmic::font::bold()),
                    )
                    .spacing(4);

                let numbers = widget::row::with_capacity(2)
                    .push(widget::text::body(&desc[numbers_txt]))
                    .push(widget::text::body(page.formatted_numbers()).font(cosmic::font::bold()))
                    .spacing(4);

                // TODO: Display measurement and paper demos

                // let measurement = widget::row::with_capacity(2)
                //     .push(widget::text::body(measurement_label.clone()))
                //     .push(widget::text::body("").font(cosmic::font::bold()))
                //     .spacing(4);

                // let paper = widget::row::with_capacity(2)
                //     .push(widget::text::body(paper_label.clone()))
                //     .push(widget::text::body("").font(cosmic::font::bold()))
                //     .spacing(4);

                let formatted_demo = widget::column::with_capacity(6)
                    .push(dates)
                    .push(time)
                    .push(dates_and_times)
                    .push(numbers)
                    // .push(measurement)
                    // .push(paper)
                    .spacing(4)
                    .padding(5.0)
                    .apply(|column| widget::settings::item_row(vec![column.into()]));

                let region = page
                    .region
                    .as_ref()
                    .map(|locale| locale.region_name.as_str())
                    .unwrap_or("");

                let select_region = crate::widget::go_next_with_item(
                    &desc[region_txt],
                    widget::text::body(region),
                    Message::RegionContext,
                );

                crate::widget::claw_section()
                    .title(&desc[formatting_txt])
                    .add(formatted_demo)
                    .add(select_region)
                    .apply(cosmic::Element::from)
                    .map(Into::into)
            })
    }
}

struct Registry(locale::Registry);

impl std::fmt::Debug for Registry {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Registry").finish()
    }
}

pub async fn page_reload() -> eyre::Result<PageRefresh> {
    let conn = zbus::Connection::system()
        .await
        .wrap_err("zbus system connection error")?;

    let registry = locale::Registry::new().wrap_err("failed to get locale registry")?;

    let system_locales: BTreeMap<String, SystemLocale> = locale1::locale1Proxy::new(&conn)
        .await
        .wrap_err("locale1 proxy connect error")?
        .locale()
        .await
        .wrap_err("could not get locale from locale1")?
        .into_iter()
        .filter_map(|expression| {
            let mut fields = expression.split('=');
            let var = fields.next()?;
            let lang_code = fields.next()?;
            let locale = registry.locale(lang_code)?;

            Some((
                var.to_owned(),
                localized_locale(&locale, lang_code.to_owned()),
            ))
        })
        .collect();

    let config = cosmic_config::Config::new("com.clawos.Settings", 1)
        .ok()
        .map(|context| {
            let locales = context
                .get::<Vec<String>>("system_locales")
                .ok()
                .unwrap_or_else(|| {
                    let current = system_locales
                        .get("LANG")
                        .map_or("en_US.UTF-8", |l| l.lang_code.as_str())
                        .to_owned();

                    vec![current]
                });

            (context, locales)
        });

    let language = system_locales
        .get("LC_ALL")
        .or_else(|| system_locales.get("LANG"))
        .cloned();

    let region = system_locales
        .get("LC_TIME")
        .or_else(|| system_locales.get("LANG"))
        .cloned();

    let mut available_languages_set = BTreeSet::new();

    // Use 'locale -a' instead of 'localectl list-locales' for OpenRC compatibility
    let output_result =
        tokio::task::spawn_blocking(|| crate::claw_glue::run_capture(&["locale", "-a"], Some(5)))
            .await
            .unwrap_or_else(|e| Err(std::io::Error::other(e.to_string())));

    let locale_list = match output_result {
        Ok(output_str) => parse_locale_output(&output_str),
        Err(why) => {
            tracing::error!(?why, "failed to list available locales using 'locale -a'");
            Vec::new()
        }
    };

    for line in locale_list {
        if let Some(locale) = registry.locale(&line) {
            available_languages_set.insert(localized_locale(&locale, line));
        }
    }

    let mut available_languages = SlotMap::new();
    for language in available_languages_set {
        available_languages.insert(language);
    }

    let language_selector_available = which::which(GNOME_LANGUAGE_SELECTOR).is_ok();

    Ok(PageRefresh {
        config,
        registry: Registry(registry),
        language,
        region,
        available_languages,
        system_locales,
        language_selector_available,
    })
}

fn language_element(
    id: usize,
    description: String,
    expanded_source_popover: Option<usize>,
    enabled: bool,
) -> cosmic::Element<'static, Message> {
    let expanded = expanded_source_popover.is_some_and(|expanded_id| expanded_id == id);

    widget::settings::item(description, popover_button(id, expanded, enabled)).into()
}

fn localized_iso_codes(locale: &locale::Locale) -> (String, String) {
    let mut language = gettextrs::dgettext("iso_639", &locale.language.display_name);
    let country = gettextrs::dgettext("iso_3166", &locale.territory.display_name);

    // Ensure language is title-cased.
    let mut chars = language.chars();
    if let Some(c) = chars.next() {
        language = c.to_uppercase().collect::<String>() + chars.as_str();
    }

    (language, country)
}

fn localized_locale(locale: &locale::Locale, lang_code: String) -> SystemLocale {
    let (language, country) = localized_iso_codes(locale);

    SystemLocale {
        lang_code,
        display_name: format!("{language} ({country})"),
        region_name: format!("{country} ({language})"),
    }
}

fn popover_button(id: usize, expanded: bool, enabled: bool) -> Element<'static, Message> {
    let on_press = Message::ExpandLanguagePopover(if expanded { None } else { Some(id) });

    let button = button::icon(widget::icon::from_name("view-more-symbolic"))
        .extra_small()
        .on_press_maybe(enabled.then_some(on_press));

    if expanded {
        widget::popover(button)
            .position(widget::popover::Position::Bottom)
            .popup(popover_menu(id))
            .on_close(Message::ExpandLanguagePopover(None))
            .into()
    } else {
        button.into()
    }
}

fn popover_menu(id: usize) -> Element<'static, Message> {
    widget::column::with_children([
        popover_menu_row(
            id,
            fl!("keyboard-sources", "move-up"),
            SourceContext::MoveUp,
        ),
        widget::divider::horizontal::default()
            .apply(widget::container)
            .padding([0, 8])
            .into(),
        popover_menu_row(
            id,
            fl!("keyboard-sources", "move-down"),
            SourceContext::MoveDown,
        ),
        widget::divider::horizontal::default()
            .apply(widget::container)
            .padding([0, 8])
            .into(),
        popover_menu_row(id, fl!("keyboard-sources", "remove"), SourceContext::Remove),
    ])
    .width(Length::Fixed(200.0))
    .apply(widget::container)
    .padding(cosmic::theme::spacing().space_xxs)
    .class(cosmic::theme::Container::Dropdown)
    .into()
}

fn popover_menu_row(
    id: usize,
    label: String,
    message: impl Fn(usize) -> SourceContext + 'static,
) -> cosmic::Element<'static, Message> {
    let spacing = cosmic::theme::spacing();
    widget::text::body(label)
        .align_y(Alignment::Center)
        .apply(button::custom)
        .padding([spacing.space_xxxs, spacing.space_xs])
        .width(Length::Fill)
        .class(cosmic::theme::Button::MenuItem)
        .on_press(Message::SourceContext(message(id)))
        .apply(Element::from)
}

fn parse_locale(locale: &str) -> Option<Locale> {
    locale
        .split('.')
        .next()?
        .replacen('_', "-", 1)
        .parse::<Locale>()
        .ok()
}

fn get_default_24h(locale: &str) -> bool {
    let Some(locale) = parse_locale(locale) else {
        return false;
    };

    let test_time = DateTime {
        date: Date::try_new_gregorian(2024, 1, 1).unwrap(),
        time: Time::try_new(13, 0, 0, 0).unwrap(),
    };

    let prefs = DateTimeFormatterPreferences::from(locale);
    let Ok(dtf) = DateTimeFormatter::try_new(prefs, fieldsets::T::medium()) else {
        return false;
    };

    let formatted = dtf.format(&test_time).to_string();

    // If we see "13" in the output, it's 24-hour format
    // If we see "1" (but not "13"), it's 12-hour format
    formatted.contains("13")
}

fn get_default_first_day(locale: &str) -> usize {
    let Some(locale) = parse_locale(locale) else {
        return 6;
    };
    let Ok(week_info) = week::WeekInformation::try_new(week::WeekPreferences::from(&locale)) else {
        return 6;
    };

    match week_info.first_weekday {
        Weekday::Monday => 0,
        Weekday::Tuesday => 1,
        Weekday::Wednesday => 2,
        Weekday::Thursday => 3,
        Weekday::Friday => 4,
        Weekday::Saturday => 5,
        Weekday::Sunday => 6,
    }
}

fn update_time_settings_after_region_change(region: &str) -> Result<(), String> {
    let config = cosmic_config::Config::new("com.clawos.AppletTime", 1)
        .map_err(|error| error.to_string())?;
    let time = config.set("military_time", get_default_24h(region));
    let week = config.set("first_day_of_week", get_default_first_day(region));
    let failures: Vec<_> = time
        .err()
        .into_iter()
        .chain(week.err())
        .map(|error| error.to_string())
        .collect();
    if failures.is_empty() {
        Ok(())
    } else {
        Err(failures.join("; "))
    }
}

/// Builds a colon-separated language list for the LANGUAGE environment variable.
/// Converts locales like ["de_DE.UTF-8", "en_US.UTF-8"] to "de_DE:de:en_US:en".
///
/// Important: The list stops at English locales since English is typically the
/// source language and doesn't need translation files. This prevents fallback
/// to other languages when English is selected.
fn build_language_list(locales: &[String]) -> String {
    let mut parts = Vec::new();

    for locale in locales {
        // Parse locale: language_TERRITORY[.CODESET][@MODIFIER]
        // We want to extract "language_TERRITORY" without codeset or modifier
        let base = strip_locale_suffix(locale);

        // Get the language-only code (e.g., "de" from "de_DE")
        let lang = base.split('_').next().unwrap_or(&base);

        // Add the full locale code (e.g., "de_DE")
        parts.push(base.clone());

        // Add the language-only code as fallback if different
        if lang != base {
            parts.push(lang.to_string());
        }

        // Stop after English - it's the source language and needs no translation
        // This matches gnome-language-selector's behavior
        if lang == "en" {
            break;
        }
    }

    parts.join(":")
}

/// Strips the codeset (.UTF-8) and modifier (@latin) from a locale string.
/// "de_DE.UTF-8" -> "de_DE"
/// "sr_RS@latin" -> "sr_RS"
/// "sr_RS.UTF-8@latin" -> "sr_RS"
fn strip_locale_suffix(locale: &str) -> String {
    // First strip the codeset (everything from '.' onwards)
    let without_codeset = locale.split('.').next().unwrap_or(locale);
    // Then strip the modifier (everything from '@' onwards)
    without_codeset
        .split('@')
        .next()
        .unwrap_or(without_codeset)
        .to_string()
}

/// Parses the output from `locale -a` command and returns a vector of locale strings.
/// Filters out pseudo-locales (C, POSIX) and accepts only allowed character encodings.
fn parse_locale_output(output: &str) -> Vec<String> {
    // Regex to match pseudo-locales: C or POSIX, optionally followed by .anything
    let pseudo_locale_re = Regex::new(r"^(C|POSIX)(\.|$)").unwrap();

    // Regex to match UTF-8 encoded locales (case-insensitive)
    // Supports optional modifiers after encoding (e.g., @euro, @valencia)
    let utf8_encoding_re = Regex::new(r"(?i)\.(utf-?8)(@.*)?$").unwrap();

    output
        .lines()
        .map(|line| line.trim())
        .filter(|line| !pseudo_locale_re.is_match(line))
        .filter(|line| utf8_encoding_re.is_match(line))
        .map(|line| line.to_string())
        .collect()
}

#[cfg(test)]
mod tests {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/unit/pages/time/region.rs"
    ));
}
