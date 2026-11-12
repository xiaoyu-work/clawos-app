use super::*;

#[test]
fn package_names_cannot_be_options_paths_or_launch_uris() {
    for name in ["curl", "python3-venv", "libfoo++", "curl:amd64"] {
        assert!(valid_package_name(name), "{name}");
    }
    for name in [
        "",
        "-oApt::Hook=id",
        "../curl",
        "a/b",
        "x\0y",
        "https://example.test",
        "a b",
    ] {
        assert!(!valid_package_name(name), "{name}");
        assert!(open(Some(name)).is_err());
    }
    assert!(!valid_package_name(&"x".repeat(256)));
}

#[test]
fn mcp_process_cannot_use_human_filesystem_adapters() {
    let previous = std::env::var_os("COS_MCP_SERVER");
    unsafe {
        std::env::set_var("COS_MCP_SERVER", "1");
    }
    assert!(crate::claw_glue::read_bytes(std::path::Path::new("/not-accessed")).is_err());
    assert!(crate::claw_glue::fs_rm(std::path::Path::new("/not-accessed")).is_err());
    let intent = crate::package::Intent {
        invocation_id: "a".repeat(32),
        action: crate::package::Action::Install,
        packages: vec!["fixture-one".into()],
    };
    let result = crate::package::refresh(&intent, crate::package::Mode::Submit);
    assert!(
        matches!(result.state, crate::package::State::Unconfirmed(ref reason)
        if reason.contains("unavailable in MCP"))
    );
    unsafe {
        match previous {
            Some(value) => std::env::set_var("COS_MCP_SERVER", value),
            None => std::env::remove_var("COS_MCP_SERVER"),
        }
    }
}

mod retained_packages {
    use crate::package::{self, Action, Intent, Mode, State, Tracked};
    use serde_json::json;
    use std::sync::Arc;

    fn intent(action: Action) -> Intent {
        Intent {
            invocation_id: "a".repeat(32),
            action,
            packages: vec!["fixture-one:amd64".into(), "fixture-two".into()],
        }
    }

    fn transaction(intent: &Intent, phase: &str, confirmed: bool) -> serde_json::Value {
        json!({
            "version": 1, "invocation_id": intent.invocation_id,
            "status": "transaction",
            "transaction": {
                "request_id": "b".repeat(32), "invocation_id": intent.invocation_id,
                "operation": intent.operation(), "phase": phase,
                "completion": {"status": "applied", "confirmed": confirmed},
            },
        })
    }

    #[test]
    fn selected_batches_are_one_exact_retained_request_not_upgrade_all_or_per_package_calls() {
        for action in [
            Action::Install,
            Action::Remove,
            Action::Purge,
            Action::Upgrade,
        ] {
            let request = intent(action).canonical().unwrap();
            let args = request.argv(Mode::Submit);
            assert_eq!(
                args,
                [
                    "__package_intent",
                    "--retained",
                    "submit",
                    &"a".repeat(32),
                    action.as_str(),
                    "fixture-one:amd64",
                    "fixture-two",
                ]
            );
            assert_eq!(
                request.operation(),
                json!({
                    "action": format!("{}-packages", action.as_str()),
                    "packages": ["fixture-one:amd64", "fixture-two"],
                })
            );
        }
        let mut request = intent(Action::Install);
        request.packages.push("fixture-one:amd64".into());
        request.packages.reverse();
        assert_eq!(request.canonical().unwrap(), intent(Action::Install));
        for name in [
            "-oHook=id",
            "/local.deb",
            "app/org.example.Flatpak/x86_64/stable",
            "*",
        ] {
            let mut request = intent(Action::Install);
            request.packages = vec![name.into()];
            assert!(request.canonical().is_err(), "{name}");
        }
    }

    #[test]
    fn retained_acceptance_and_review_ready_are_never_package_success() {
        let request = intent(Action::Install);
        for value in [
            json!({
                "version": 1, "invocation_id": request.invocation_id,
                "status": "accepted", "receipt": {
                    "accepted": true, "status": "accepted", "request_id": "b".repeat(32),
                    "invocation_id": request.invocation_id, "completion": "query_required",
                },
            }),
            json!({"version": 1, "invocation_id": request.invocation_id, "status": "permission_ready"}),
            transaction(&request, "planning", true),
            transaction(&request, "cleanup_pending", true),
            transaction(&request, "indeterminate", true),
            transaction(&request, "applied", false),
        ] {
            let tracked = Tracked {
                intent: request.clone(),
                state: package::decode(&request, value).unwrap(),
            };
            assert!(!tracked.confirmed_applied());
            assert!(!tracked.terminal());
        }
        let applied = package::decode(&request, transaction(&request, "applied", true)).unwrap();
        assert!(
            Tracked {
                intent: request.clone(),
                state: applied
            }
            .confirmed_applied()
        );
        let mut recovery = transaction(&request, "applied", true);
        recovery["status"] = json!("recovery_requested");
        let recovery = package::decode(&request, recovery).unwrap();
        assert!(matches!(recovery, State::RecoveryRequested(_)));
        assert!(
            !Tracked {
                intent: request,
                state: recovery
            }
            .confirmed_applied()
        );
    }

    #[test]
    fn completion_requires_matching_root_correlation_operation_and_evidence() {
        let request = intent(Action::Remove);
        let good = transaction(&request, "applied", true);
        for (field, value) in [
            ("invocation_id", json!("c".repeat(32))),
            ("operation", json!({"action": "upgrade-all"})),
            ("request_id", json!("not-a-root-receipt")),
            ("phase", json!("success")),
        ] {
            let mut wrong = good.clone();
            wrong["transaction"][field] = value;
            assert!(package::decode(&request, wrong).is_err(), "{field}");
        }
        assert!(package::decode(&request, json!({"installed": true})).is_err());
        let mut injected = good;
        injected["approved"] = json!(true);
        assert!(package::decode(&request, injected).is_err());
    }

    #[test]
    fn flatpak_and_local_deb_never_enter_the_debian_intent_transport() {
        let info = Arc::new(crate::AppInfo {
            pkgnames: vec!["fixture-one".into()],
            ..Default::default()
        });
        let mut operation = crate::Operation {
            kind: crate::OperationKind::Install,
            backend_name: crate::backend::BackendName::FlatpakUser,
            package_ids: vec![crate::AppId::new("org.example.Fixture")],
            infos: vec![info],
        };
        assert!(Intent::for_operation(&operation).is_err());
        operation.backend_name = crate::backend::BackendName::Packagekit;
        Arc::make_mut(&mut operation.infos[0])
            .package_paths
            .push("/local.deb".into());
        assert!(
            Intent::for_operation(&operation)
                .unwrap_err()
                .to_string()
                .contains("OS_PACKAGE_SOURCE_UNSUPPORTED")
        );
    }
}
