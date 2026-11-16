// SPDX-License-Identifier: GPL-3.0-only

pub async fn list() -> Result<cosmic_randr_shell::List, cosmic_randr_shell::Error> {
    let response = cosmic_settings_provider_client::call_async("display", "status", vec![])
        .await
        .map_err(|error| cosmic_randr_shell::Error::Spawn(std::io::Error::other(error)))?;
    let kdl = response["kdl"]
        .as_str()
        .filter(|value| value.len() <= 1024 * 1024)
        .ok_or_else(|| {
            cosmic_randr_shell::Error::Spawn(std::io::Error::other(
                cosmic_settings_provider_client::refused(
                    "OS display metadata is unavailable or oversized",
                ),
            ))
        })?;
    let document = kdl
        .parse::<kdl::KdlDocument>()
        .map_err(cosmic_randr_shell::Error::Kdl)?;
    cosmic_randr_shell::List::try_from(document).map_err(|error| {
        cosmic_randr_shell::Error::Spawn(std::io::Error::other(
            cosmic_settings_provider_client::refused(format!(
                "OS display metadata is invalid: {:?}",
                error.errors
            )),
        ))
    })
}
