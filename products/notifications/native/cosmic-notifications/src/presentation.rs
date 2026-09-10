// SPDX-License-Identifier: GPL-3.0-only

#[path = "presentation/images.rs"]
mod images;

use anyhow::Result;
use claw_notification_presentation::{Card, Preferences, TextRun, VERSION};
use cosmic::{
    cosmic_config::{Config, ConfigGet, ConfigSet, CosmicConfigEntry},
    iced::font::{Style, Weight},
};
use cosmic_notifications_config::NotificationsConfig;
use cosmic_notifications_util::{ActionId, Notification, markup};
use images::{image_icon, named_icon};

pub fn config() -> Result<Config> {
    Ok(Config::new(
        cosmic_notifications_config::ID,
        NotificationsConfig::VERSION,
    )?)
}

pub fn preferences(config: &Config) -> Result<Preferences> {
    let muted = match config.get("do_not_disturb") {
        Ok(value) => value,
        // A missing system-default directory is also an unconfigured key.
        Err(
            cosmic::cosmic_config::Error::NotFound
            | cosmic::cosmic_config::Error::NoConfigDirectory,
        ) => NotificationsConfig::default().do_not_disturb,
        Err(error) => return Err(error.into()),
    };
    Ok(Preferences::new(muted))
}

pub fn set_preferences(config: &Config, payload: &str) -> Result<Preferences> {
    let value = Preferences::from_json(payload)?;
    config.set("do_not_disturb", value.muted)?;
    preferences(config)
}

pub fn card(notification: &Notification) -> Result<Card> {
    anyhow::ensure!(
        notification.body.len() <= claw_notification_presentation::MAX_TEXT_BYTES,
        "notification markup exceeds the presentation limit"
    );
    let body = markup::html_to_spans(&notification.body)
        .into_iter()
        .map(|span| TextRun {
            text: span.text.to_string(),
            bold: span.font.is_some_and(|font| font.weight == Weight::Bold),
            italic: span.font.is_some_and(|font| font.style == Style::Italic),
            underline: span.underline,
            accent: span.color.is_some(),
        })
        .collect();
    let app_icon = (!notification.app_icon.is_empty())
        .then(|| named_icon(&notification.app_icon))
        .transpose()?
        .flatten();
    let image = notification.image().map(image_icon).transpose()?.flatten();
    let activation = notification
        .actions
        .iter()
        .find(|action| action.0 == ActionId::Default)
        .or_else(|| notification.actions.first())
        .map(|action| action.0.to_string());
    let value = Card {
        version: VERSION,
        id: notification.id,
        source_label: notification.app_name.clone(),
        title: notification.summary.clone(),
        body,
        activation,
        icon: image.clone().or_else(|| app_icon.clone()),
        group_icon: app_icon.or(image),
    };
    value.validate()?;
    Ok(value)
}

#[cfg(test)]
mod tests {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/unit/presentation.rs"
    ));
}
