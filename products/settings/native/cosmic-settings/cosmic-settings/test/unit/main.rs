// SPDX-License-Identifier: GPL-3.0-only

use super::*;
use std::ffi::{OsStr, OsString};

fn launch_args<I, T>(argv: I, gui: bool) -> Result<Args, clap::Error>
where
    I: IntoIterator<Item = T>,
    T: Into<OsString>,
{
    Args::try_parse_from(claw_app_gui_argv::normalize(
        argv.into_iter().map(Into::into),
        gui,
        OsStr::new("--gui"),
    ))
}

fn result_text(value: Result<Args, clap::Error>) -> String {
    match value {
        Ok(args) => format!("{args:?}"),
        Err(error) => format!("{}:{:?}:{error}", error.exit_code(), error.kind()),
    }
}

#[test]
fn native_gui_argv_preserves_the_actual_settings_parser() {
    let cases: &[&[&str]] = &[
        &[],
        &["appearance"],
        &["appearance", "import", "theme with spaces.ron"],
        &["appearance", "export", "--", "--gui"],
        &["appearance", "import", "file:///theme.ron"],
        &["appearance", "import"],
        &["appearance", "import", "one.ron", "two.ron"],
        &["appearance", "--help"],
        &["--help"],
        &["--version"],
        &["--unknown"],
        &["--", "--gui"],
    ];
    for arguments in cases {
        let direct = std::iter::once("cosmic-settings").chain(arguments.iter().copied());
        let gui = ["cosmic-settings", "--gui"]
            .into_iter()
            .chain(arguments.iter().copied());
        assert_eq!(
            result_text(launch_args(direct, false)),
            result_text(launch_args(gui, true)),
            "{arguments:?}",
        );
    }
}

#[test]
fn native_gui_argv_consumes_only_the_host_selector() {
    let direct = launch_args(["cosmic-settings", "--gui"], false).unwrap_err();
    assert_eq!(direct.kind(), clap::error::ErrorKind::UnknownArgument);
    let repeated = launch_args(["cosmic-settings", "--gui", "--gui"], true).unwrap_err();
    assert_eq!(direct.to_string(), repeated.to_string());
    assert!(launch_args(["cosmic-settings"], true).is_ok());
}

#[test]
fn native_gui_argv_preserves_end_of_options_theme_paths() {
    let args = launch_args(
        [
            "cosmic-settings",
            "--gui",
            "appearance",
            "import",
            "--",
            "--gui",
        ],
        true,
    )
    .unwrap();
    let Some(PageCommands::Appearance {
        command: Some(AppearanceCommands::Import { path }),
    }) = args.sub_command
    else {
        panic!("appearance import was not preserved");
    };
    assert_eq!(path, PathBuf::from("--gui"));
}

#[test]
fn native_gui_argv_retains_early_help_and_version() {
    for (flag, kind) in [
        ("--help", clap::error::ErrorKind::DisplayHelp),
        ("--version", clap::error::ErrorKind::DisplayVersion),
    ] {
        let error = launch_args(["cosmic-settings", "--gui", flag], true).unwrap_err();
        assert_eq!(error.kind(), kind);
        assert_eq!(error.exit_code(), 0);
    }
}

#[cfg(unix)]
#[test]
fn native_gui_argv_preserves_non_utf8_theme_paths() {
    use std::os::unix::ffi::OsStringExt;

    let path = OsString::from_vec(b"theme-\xff.ron".to_vec());
    let args = launch_args(
        [
            OsString::from("cosmic-settings"),
            OsString::from("--gui"),
            OsString::from("appearance"),
            OsString::from("export"),
            path.clone(),
        ],
        true,
    )
    .unwrap();
    let Some(PageCommands::Appearance {
        command: Some(AppearanceCommands::Export { path: parsed }),
    }) = args.sub_command
    else {
        panic!("appearance export was not preserved");
    };
    assert_eq!(parsed, PathBuf::from(path));
}

#[cfg(feature = "page-users")]
mod users_service {
    use crate::{
        regional_settings::Failure,
        user_settings::{self, Change, Target},
    };
    use serde_json::{Value, json};

    fn target() -> Target {
        Target {
            user: "fixture_user".into(),
            uid: 1001,
        }
    }

    fn response(action: &str, value: Value) -> Value {
        json!({
            "action":action,"status":"applied","user":"fixture_user","uid":1001,
            "value":value,"home":"/home/original-home","rollback_supported":false,
        })
    }

    #[test]
    fn users_service_maps_the_actual_fields_to_closed_uid_bound_root_arguments() {
        for (change, action, field, value) in [
            (
                Change::FullName(target(), "Fixture User".into()),
                "set-full-name",
                "--full-name",
                "Fixture User",
            ),
            (
                Change::Rename(target(), "renamed_user".into()),
                "rename-user",
                "--new-name",
                "renamed_user",
            ),
            (
                Change::Icon(target(), "/home/fixture/profile.png".into()),
                "set-icon",
                "--icon",
                "/home/fixture/profile.png",
            ),
            (
                Change::AccountType(target(), true),
                "set-account-type",
                "--account-type",
                "administrator",
            ),
            (
                Change::AccountType(target(), false),
                "set-account-type",
                "--account-type",
                "standard",
            ),
            (
                Change::Password(target(), "default/fixture-password".into()),
                "set-password",
                "--credential",
                "default/fixture-password",
            ),
        ] {
            assert_eq!(
                change.argv().unwrap(),
                [
                    "__users",
                    action,
                    "--user",
                    "fixture_user",
                    "--uid",
                    "1001",
                    field,
                    value,
                ]
            );
        }
        assert_eq!(
            Change::Delete(target()).argv().unwrap(),
            [
                "__users",
                "delete-user",
                "--user",
                "fixture_user",
                "--uid",
                "1001",
                "--confirm",
            ]
        );
        assert!(
            Change::Password(target(), "inline password".into())
                .argv()
                .is_err()
        );
        let bounded = format!("{}/{}", "n".repeat(127), "k".repeat(128));
        assert!(Change::Password(target(), bounded.clone()).argv().is_ok());
        assert!(Change::Password(target(), format!("{bounded}x")).argv().is_err());
        assert!(
            Change::Create {
                user: "fixture_user".into(),
                full_name: "Fixture User".into(),
                credential: "plaintext-is-not-a-reference".into(),
                administrator: true,
            }
            .argv()
            .is_err()
        );
    }

    #[test]
    fn users_service_requires_matching_root_target_value_and_unambiguous_confirmation() {
        let change = Change::Rename(target(), "renamed_user".into());
        let valid = response("rename-user", json!("renamed_user"));
        user_settings::decode(&change, valid.clone()).unwrap();
        for (field, value) in [
            ("uid", json!(1002)),
            ("user", json!("another_user")),
            ("status", json!("pending")),
            ("action", json!("set-full-name")),
            ("value", json!("another_name")),
            ("rollback_supported", json!(true)),
            ("approved", json!(true)),
        ] {
            let mut bad = valid.clone();
            bad[field] = value;
            assert!(user_settings::decode(&change, bad).is_err(), "{field}");
        }
        let icon = Change::Icon(target(), "/home/fixture/profile.png".into());
        user_settings::decode(
            &icon,
            response("set-icon", json!("/home/fixture/profile.png")),
        )
        .unwrap();
        assert!(
            user_settings::decode(
                &icon,
                response("set-icon", json!("/home/fixture/another.png"))
            )
            .is_err()
        );
        let password = Change::Password(target(), "default/fixture-password".into());
        let valid = json!({
            "action":"set-password","user":"fixture_user","uid":1001,
            "state":{"kind":"user","present":true,"record":{"name":"fixture_user","uid":1001}},
        });
        user_settings::decode(&password, valid.clone()).unwrap();
        let mut bad = valid;
        bad["state"]["record"]["uid"] = json!(1002);
        assert!(user_settings::decode(&password, bad).is_err());
    }

    #[test]
    fn users_service_creation_stops_at_the_first_unconfirmed_step_without_retry_or_delete() {
        use std::{cell::RefCell, collections::VecDeque, future::ready};
        let runtime = tokio::runtime::Builder::new_current_thread()
            .build()
            .unwrap();
        let calls = RefCell::new(Vec::new());
        let responses = RefCell::new(VecDeque::from([
            Ok(json!({
                "action":"create-user","state":{"kind":"user","present":true,"record":{"name":"fixture_user","uid":1001}},
            })),
            Err(Failure::Denied(
                "missing exact password credential grant".into(),
            )),
        ]));
        let result = runtime.block_on(user_settings::apply_with(
            Change::Create {
                user: "fixture_user".into(),
                full_name: "Fixture User".into(),
                credential: "default/fixture-password".into(),
                administrator: true,
            },
            |args| {
                calls.borrow_mut().push(args);
                ready(
                    responses
                        .borrow_mut()
                        .pop_front()
                        .expect("unexpected retry/fallback"),
                )
            },
        ));
        let Err(Failure::Unconfirmed(message)) = result else {
            panic!("partial creation was reported successful")
        };
        assert!(message.contains("account was created"));
        assert!(message.contains("set-password"));
        assert!(message.contains("no rollback"));
        assert_eq!(
            calls
                .borrow()
                .iter()
                .map(|args| args[1].as_str())
                .collect::<Vec<_>>(),
            ["create-user", "set-password",]
        );
        assert_eq!(
            calls.borrow()[1],
            [
                "__users",
                "set-password",
                "--user",
                "fixture_user",
                "--uid",
                "1001",
                "--credential",
                "default/fixture-password",
            ]
        );
    }
}
