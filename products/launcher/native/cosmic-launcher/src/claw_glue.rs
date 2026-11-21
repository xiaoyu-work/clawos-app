// SPDX-License-Identifier: GPL-3.0-only

pub fn ask_claw(query: &str) -> Result<(), cos_runtime::ask_claw::LaunchError> {
    cos_runtime::ask_claw::launch_query(query)
}

pub async fn open_desktop_entry(id: &str) -> Result<(), String> {
    let response = claw_os_sdk::cos_call_json_async_with_binary(
        "/usr/local/bin/yu",
        "desktop",
        "launch",
        ["__desktop-menu", "run", id],
    )
    .await
    .map_err(|error| error.to_string())?;
    if response["status"] != "submitted" {
        return Err("Claw OS did not confirm opening the application.".into());
    }
    Ok(())
}
