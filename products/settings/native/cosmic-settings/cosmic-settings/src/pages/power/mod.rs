mod backend;

use backend::{Battery, ConnectedDevice, PowerProfile};

use crate::owner_config::{Config, CosmicConfigEntry};
use cosmic::Task;
use cosmic::iced::core::text::{Ellipsize, EllipsizeHeightLimit};
use cosmic::iced::widget::{column, row};
use cosmic::iced::{self, Alignment, Length, stream};
use cosmic::widget::{self, settings, space, text};
use cosmic::{Apply, surface};
use cosmic_idle_config::CosmicIdleConfig;
use cosmic_settings_page::{self as page, Section, section};
use futures::SinkExt;
use itertools::Itertools;
use slab::Slab;
use slotmap::SlotMap;
use std::iter;
use std::time::Duration;

static SCREEN_OFF_TIMES: &[Duration] = &[
    Duration::from_secs(2 * 60),
    Duration::from_secs(5 * 60),
    Duration::from_secs(10 * 60),
    Duration::from_secs(15 * 60),
    Duration::from_secs(30 * 60),
];

static SUSPEND_TIMES: &[Duration] = &[
    Duration::from_secs(15 * 60),
    Duration::from_secs(20 * 60),
    Duration::from_secs(25 * 60),
    Duration::from_secs(30 * 60),
    Duration::from_secs(45 * 60),
    Duration::from_secs(60 * 60),
    Duration::from_secs(80 * 60),
    Duration::from_secs(90 * 60),
    Duration::from_secs(100 * 60),
    Duration::from_secs(2 * 60 * 60),
];

fn format_time(duration: Duration) -> String {
    let m = duration.as_secs() / 60;
    if m.is_multiple_of(60) {
        fl!("x-hours", number = (m / 60))
    } else {
        fl!("x-minutes", number = m)
    }
}

pub struct Page {
    entity: page::Entity,
    battery: Battery,
    connected_devices: Vec<ConnectedDevice>,
    on_enter_handle: Option<cosmic::iced::task::Handle>,
    screen_off_labels: Vec<String>,
    suspend_labels: Vec<String>,
    idle_config: Config,
    idle_conf: CosmicIdleConfig,
    backend: Option<backend::PowerBackendEnum>,
    current_power_profile: Option<PowerProfile>,
    pending: bool,
    notice: Option<String>,
}

impl Default for Page {
    fn default() -> Self {
        let idle_config = Config::new("com.clawos.Idle", 1).unwrap();
        let idle_conf = CosmicIdleConfig::get_entry(&idle_config).unwrap_or_else(|(_, conf)| conf);

        Self {
            entity: Default::default(),
            battery: Default::default(),
            connected_devices: Vec::new(),
            on_enter_handle: None,
            screen_off_labels: SCREEN_OFF_TIMES
                .iter()
                .copied()
                .map(format_time)
                .chain(iter::once(fl!("never")))
                .collect(),
            suspend_labels: SUSPEND_TIMES
                .iter()
                .copied()
                .map(format_time)
                .chain(iter::once(fl!("never")))
                .collect(),
            idle_config,
            idle_conf,
            backend: None,
            current_power_profile: None,
            pending: false,
            notice: None,
        }
    }
}

impl page::Page<crate::pages::Message> for Page {
    fn set_id(&mut self, entity: page::Entity) {
        self.entity = entity;
    }

    fn info(&self) -> page::Info {
        page::Info::new("power", "preferences-power-and-battery-symbolic")
            .title(fl!("power"))
            .description(fl!("xdg-entry-power-comment"))
    }

    fn content(
        &self,
        sections: &mut SlotMap<section::Entity, Section<crate::pages::Message>>,
    ) -> Option<page::Content> {
        Some(vec![
            sections.insert(provider_status()),
            sections.insert(battery_info()),
            sections.insert(connected_devices()),
            sections.insert(profiles()),
            sections.insert(power_saving()),
        ])
    }

    fn subscription(
        &self,
        _core: &cosmic::Core,
    ) -> cosmic::iced::Subscription<crate::pages::Message> {
        iced::Subscription::run(|| {
            stream::channel(
                1,
                |mut sender: futures::channel::mpsc::Sender<crate::pages::Message>| async move {
                    loop {
                        if sender
                            .send(Message::Snapshot(backend::snapshot().await).into())
                            .await
                            .is_err()
                        {
                            return;
                        }
                        tokio::time::sleep(Duration::from_secs(5)).await;
                    }
                },
            )
        })
    }

    fn on_enter(&mut self) -> cosmic::Task<crate::pages::Message> {
        let (task, handle) = cosmic::Task::future(async {
            Message::BackendAvailabilityCheck(backend::get_backend().await)
        })
        .map(crate::pages::Message::Power)
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

#[derive(Clone, Debug)]
pub enum Message {
    Snapshot(Result<backend::Snapshot, String>),
    ProfileFinished(Result<PowerProfile, String>),
    PowerProfileChange(PowerProfile),
    /// Update the system battery
    UpdateBattery(Battery),
    /// Update the battery of a connected device
    UpdateDeviceBattery(String, Battery),
    UpdateConnectedDevices(Vec<ConnectedDevice>),
    DeviceDisconnect(String),
    DeviceConnect(ConnectedDevice),
    ScreenOffTimeChange(Option<Duration>),
    SuspendOnAcTimeChange(Option<Duration>),
    SuspendOnBatteryTimeChange(Option<Duration>),
    BackendAvailabilityCheck(Option<backend::PowerBackendEnum>),
    CurrentPowerProfileUpdate(PowerProfile),
    Surface(surface::Action),
}

impl From<Message> for crate::app::Message {
    fn from(message: Message) -> Self {
        crate::pages::Message::Power(message).into()
    }
}

impl From<Message> for crate::pages::Message {
    fn from(message: Message) -> Self {
        crate::pages::Message::Power(message)
    }
}

impl Page {
    pub fn update(&mut self, message: Message) -> Task<crate::app::Message> {
        match message {
            Message::PowerProfileChange(p) => {
                if !self.pending
                    && let Some(ref backend) = self.backend
                {
                    self.pending = true;
                    self.notice = Some(fl!("regional-settings", "working"));
                    let backend = backend.clone();
                    return cosmic::Task::future(async move {
                        crate::app::Message::PageMessage(crate::pages::Message::Power(
                            Message::ProfileFinished(backend.set_power_profile(p).await),
                        ))
                    });
                }
            }
            Message::ProfileFinished(result) => {
                self.pending = false;
                match result {
                    Ok(profile) => {
                        self.current_power_profile = Some(profile);
                        self.notice = None;
                    }
                    Err(error) => self.notice = Some(error),
                }
            }
            Message::Snapshot(result) => match result {
                Ok(snapshot) => {
                    self.battery = snapshot.battery;
                    self.connected_devices = snapshot.devices;
                }
                Err(error) => self.notice = Some(error),
            },
            Message::UpdateBattery(battery) => self.battery = battery,
            Message::UpdateDeviceBattery(path, battery) => {
                for device in &mut self.connected_devices {
                    if device.device_path == path {
                        device.battery = battery;
                        break;
                    }
                }
            }
            Message::UpdateConnectedDevices(connected_devices) => {
                self.connected_devices = connected_devices;
            }
            Message::ScreenOffTimeChange(time) => {
                let time = time.map(|x| x.as_millis() as u32);
                if let Err(err) = self.idle_config.edit(&mut self.idle_conf, |entry, local| {
                    entry.set_screen_off_time(local, time)
                }) {
                    tracing::error!("failed to set screen off time: {}", err)
                }
            }
            Message::SuspendOnAcTimeChange(time) => {
                let time = time.map(|x| x.as_millis() as u32);
                if let Err(err) = self.idle_config.edit(&mut self.idle_conf, |entry, local| {
                    entry.set_suspend_on_ac_time(local, time)
                }) {
                    tracing::error!("failed to set suspend on ac time: {}", err)
                }
            }
            Message::SuspendOnBatteryTimeChange(time) => {
                let time = time.map(|x| x.as_millis() as u32);
                if let Err(err) = self.idle_config.edit(&mut self.idle_conf, |entry, local| {
                    entry.set_suspend_on_battery_time(local, time)
                }) {
                    tracing::error!("failed to set suspend on battery time: {}", err)
                }
            }
            Message::DeviceDisconnect(device_path) => self
                .connected_devices
                .retain(|device| device.device_path != device_path),
            Message::DeviceConnect(new_device) => {
                // If a connected device already exists at a path, replace it.
                if let Some(old) = self
                    .connected_devices
                    .iter_mut()
                    .find(|existing| existing.device_path == new_device.device_path)
                {
                    *old = new_device;
                } else {
                    self.connected_devices.push(new_device)
                }
            }
            Message::Surface(a) => {
                return cosmic::task::message(crate::app::Message::Surface(a));
            }
            Message::BackendAvailabilityCheck(backend) => {
                self.current_power_profile = backend.as_ref().map(|backend| backend.current);
                self.backend = backend;
            }
            Message::CurrentPowerProfileUpdate(profile) => {
                self.current_power_profile = Some(profile);
            }
        };
        Task::none()
    }
}

fn provider_status() -> Section<crate::pages::Message> {
    Section::default()
        .show_while::<Page>(|page| page.notice.is_some())
        .view::<Page>(|_, page, _| {
            widget::text::body(page.notice.as_deref().unwrap_or_default()).into()
        })
}

fn battery_info() -> Section<crate::pages::Message> {
    let descriptions = Slab::new();

    Section::default()
        .title(fl!("battery"))
        .descriptions(descriptions)
        .show_while::<Page>(|page| page.battery.is_present)
        .view::<Page>(move |_binder, page, section| {
            let battery_icon = widget::icon::from_name(page.battery.icon_name.clone());
            let remaining_time = page.battery.remaining_time();
            let battery_label = text::body(if remaining_time.is_empty() {
                format!("{:.0}%", page.battery.percent)
            } else {
                format!("{:.0}% ({})", page.battery.percent, remaining_time)
            });

            widget::column::with_capacity(2)
                .push(text::heading(&section.title))
                .push(
                    row!(battery_icon, battery_label)
                        .align_y(Alignment::Center)
                        .spacing(cosmic::theme::active().cosmic().space_xxxs()),
                )
                .into()
        })
}

fn connected_devices() -> Section<crate::pages::Message> {
    let descriptions = Slab::new();

    Section::default()
        .title(fl!("connected-devices"))
        .descriptions(descriptions)
        .show_while::<Page>(|page| !page.connected_devices.is_empty())
        .view::<Page>(move |_binder, page, section| {
            let devices: Vec<cosmic::Element<'_, _>> = page
                .connected_devices
                .iter()
                .map(|connected_device| {
                    let battery_icon =
                        widget::icon::from_name(connected_device.battery.icon_name.clone());

                    let battery_percent_and_time = widget::text(
                        if connected_device.battery.remaining_duration.is_positive() {
                            format!(
                                "{}% - {}",
                                connected_device.battery.percent,
                                &connected_device.battery.remaining_time()
                            )
                        } else {
                            format!("{}%", connected_device.battery.percent)
                        },
                    );
                    widget::container(
                        row!(
                            widget::icon::from_name(connected_device.device_icon).size(48),
                            column!(
                                text::heading(&connected_device.model)
                                    .ellipsize(Ellipsize::End(EllipsizeHeightLimit::Lines(1)))
                                    .height(20.0)
                                    .width(Length::Fill),
                                row!(battery_icon, battery_percent_and_time)
                                    .spacing(4)
                                    .align_y(Alignment::Center),
                            )
                            .height(Length::Shrink)
                        )
                        .align_y(Alignment::Center)
                        .spacing(16)
                        .padding([8, 16])
                        .width(Length::Fill)
                        .height(Length::Fill),
                    )
                    .height(64.)
                    .class(crate::theme::section_card())
                    .into()
                })
                .collect();

            widget::column::with_capacity(2)
                .spacing(8)
                .push(text::heading(&section.title))
                .push(
                    widget::column::with_capacity(devices.len())
                        .extend(
                            devices
                                .into_iter()
                                .chunks(2)
                                .into_iter()
                                .map(|mut device_row| {
                                    cosmic::Element::from(
                                        row!(
                                            device_row.next().unwrap_or(space::horizontal().into()),
                                            device_row.next().unwrap_or(space::horizontal().into()),
                                        )
                                        .spacing(8),
                                    )
                                }),
                        )
                        .spacing(8),
                )
                .into()
        })
}

fn profiles() -> Section<crate::pages::Message> {
    crate::slab!(descriptions {
        _power_desc = fl!("xdg-entry-power-comment");
    });

    Section::default()
        .title(fl!("power-mode"))
        .descriptions(descriptions)
        .view::<Page>(move |_binder, page, section| {
            let mut section = crate::widget::claw_section().title(&section.title);

            if page.backend.is_some() {
                let profiles = backend::get_power_profiles();

                if let Some(current_profile) = page.current_power_profile {
                    section = profiles
                        .into_iter()
                        .map(|profile| {
                            settings::item::builder(profile.title())
                                .description(profile.description())
                                .radio(profile, Some(current_profile), Message::PowerProfileChange)
                        })
                        .fold(section, settings::Section::add);
                }
            } else {
                let item = text::body(fl!("power-mode", "no-backend"));
                section = section.add(item);
            }

            section
                .apply(cosmic::Element::from)
                .map(crate::pages::Message::Power)
        })
}

fn power_saving_row<'a>(
    label: &'a str,
    labels: &'a [String],
    selected_time: Option<Duration>,
    times: &'static [Duration],
    on_select: fn(Option<Duration>) -> Message,
) -> cosmic::Element<'a, Message> {
    let selected = if let Some(time) = selected_time {
        times.iter().position(|x| *x == time)
    } else {
        // "Never"
        Some(times.len())
    };

    settings::item(
        label,
        widget::dropdown::popup_dropdown(
            labels,
            selected,
            move |i| on_select(times.get(i).copied()),
            cosmic::iced::window::Id::RESERVED,
            Message::Surface,
            |a| crate::app::Message::PageMessage(crate::pages::Message::Power(a)),
        ),
    )
    .into()
}

fn power_saving() -> Section<crate::pages::Message> {
    let mut descriptions = Slab::new();

    let turn_off_screen_desc = descriptions.insert(fl!("power-saving", "turn-off-screen-after"));
    let auto_suspend_desc = descriptions.insert(fl!("power-saving", "auto-suspend"));
    let auto_suspend_ac_desc = descriptions.insert(fl!("power-saving", "auto-suspend-ac"));
    let auto_suspend_battery_desc =
        descriptions.insert(fl!("power-saving", "auto-suspend-battery"));

    Section::default()
        .title(fl!("power-saving"))
        .descriptions(descriptions)
        .view::<Page>(move |_binder, page, section| {
            let descriptions = &section.descriptions;
            let screen_off_time = page
                .idle_conf
                .screen_off_time
                .map(|t| Duration::from_millis(t.into()));
            let suspend_on_ac_time = page
                .idle_conf
                .suspend_on_ac_time
                .map(|t| Duration::from_millis(t.into()));
            let suspend_on_battery_time = page
                .idle_conf
                .suspend_on_battery_time
                .map(|t| Duration::from_millis(t.into()));
            let mut section = crate::widget::claw_section()
                .title(&section.title)
                .add(power_saving_row(
                    &descriptions[turn_off_screen_desc],
                    &page.screen_off_labels,
                    screen_off_time,
                    SCREEN_OFF_TIMES,
                    Message::ScreenOffTimeChange,
                ))
                .add(power_saving_row(
                    &descriptions[if page.battery.is_present {
                        auto_suspend_ac_desc
                    } else {
                        auto_suspend_desc
                    }],
                    &page.suspend_labels,
                    suspend_on_ac_time,
                    SUSPEND_TIMES,
                    Message::SuspendOnAcTimeChange,
                ));
            if page.battery.is_present {
                section = section.add(power_saving_row(
                    &descriptions[auto_suspend_battery_desc],
                    &page.suspend_labels,
                    suspend_on_battery_time,
                    SUSPEND_TIMES,
                    Message::SuspendOnBatteryTimeChange,
                ));
            }
            section
                .apply(cosmic::Element::from)
                .map(crate::pages::Message::Power)
        })
}

impl page::AutoBind<crate::pages::Message> for Page {}
