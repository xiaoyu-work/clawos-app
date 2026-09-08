import json
import os
import pathlib
import sys
from unittest import mock

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(
    pathlib.Path(__file__).with_name("main.py"),
    "claw_test_printer_manager_main",
    clear_modules=("_shared",),
)


@pytest.fixture(params=["direct", "mcp"])
def invoke(request):
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {
            "COS_APP_MANIFEST": str(pathlib.Path(__file__).with_name("app.json")),
        },
    ):
        server = load_local_module(
            pathlib.Path(__file__).with_name("server.py"),
            "claw_test_printer_manager_server",
        )
        listed = server.app._handle_request("tools/list", {}, True)
        assert {tool["name"] for tool in listed["tools"]} == {
            f"printer-manager.{name}" for name in ["status", "capabilities", "jobs", "print", "cancel"]
        }

        def call(action, **arguments):
            if request.param == "direct":
                function = main.print_document if action == "print" else getattr(main, action)
                return function(**arguments)
            response = server.app._handle_request(
                "tools/call",
                authenticated_mcp_params({
                    "name": f"printer-manager.{action}", "arguments": arguments,
                }),
                True,
            )
            return response["structuredContent"]

        yield call


def test_manifest_keeps_separate_scopes_and_cancel_confirmation():
    manifest = json.loads(pathlib.Path(__file__).with_name("app.json").read_text())
    assert "operations" not in manifest
    tools = {tool["name"]: tool for tool in manifest["mcp"]["tools"]}
    for action, verb, scope in [
        ("status", "sys.observe", "printing"),
        ("capabilities", "sys.observe", "printing"),
        ("jobs", "device.printer", "observe"),
        ("print", "device.printer", "print"),
        ("cancel", "device.printer", "control"),
    ]:
        expected = [(verb, {"kind": "fixed", "scope": {"kind": "name", "value": scope}})]
        if action == "print":
            expected.append(("fs.read", {"kind": "from-arg", "arg": "source"}))
        assert [
            (need["verb"], need["scope"]) for need in tools[f"printer-manager.{action}"]["needs"]
        ] == expected
    assert tools["printer-manager.cancel"]["args"][-1] == {
        "name": "confirm", "kind": "bool", "required": True,
        "binding": "flag", "choices": [True],
    }


def _completed(payload: object, returncode: int = 0) -> mock.Mock:
    return mock.Mock(
        returncode=returncode,
        stdout=json.dumps(payload),
        stderr="",
    )


def test_status_uses_printing_observe_scope(invoke):
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess, "run", return_value=_completed({"printers": []})
    ) as run:
        result = invoke("status")
    require.assert_called_once_with("sys.observe", name="printing")
    assert run.call_args.args[0] == ["/usr/local/bin/cos", "__printer", "status"]
    assert result == {"printers": []}


def test_capabilities_uses_printing_observe_scope(invoke):
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess, "run", return_value=_completed({"capabilities": []})
    ) as run:
        result = invoke("capabilities", printer="office")
    require.assert_called_once_with("sys.observe", name="printing")
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos",
        "__printer",
        "capabilities",
        "--printer",
        "office",
    ]
    assert result == {"capabilities": []}


@pytest.mark.parametrize("printer", [None, "office"])
def test_jobs_uses_printer_observe_scope_and_optional_printer(invoke, printer):
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess, "run", return_value=_completed({"jobs": []})
    ) as run:
        result = invoke("jobs", **({} if printer is None else {"printer": printer}))
    require.assert_called_once_with("device.printer", name="observe")
    expected = ["/usr/local/bin/cos", "__printer", "jobs"]
    if printer is not None:
        expected.extend(["--printer", printer])
    assert run.call_args.args[0] == expected
    assert result == {"jobs": []}


@pytest.mark.parametrize(
    "options",
    [
        {},
        *[
            {"sides": sides, "copies": 2, "title": "Quarterly report", "media": "A4"}
            for sides in ["one-sided", "two-sided-long-edge", "two-sided-short-edge"]
        ],
    ],
)
def test_print_uses_exact_scopes_and_safe_arguments(invoke, options):
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.os.path, "realpath", side_effect=lambda value: value
    ), mock.patch.object(main.os.path, "islink", return_value=False), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess, "run", return_value=_completed({"job_id": "office-1"})
    ) as run:
        result = invoke(
            "print",
            printer="office",
            source="/home/user/document.pdf",
            **options,
        )
    assert require.call_args_list == [
        mock.call("device.printer", name="print"),
        mock.call("fs.read", path="/home/user/document.pdf"),
    ]
    expected = [
        "/usr/local/bin/cos",
        "__printer",
        "print",
        "--printer",
        "office",
        "--source",
        "/home/user/document.pdf",
    ]
    if options:
        expected.extend([
            "--title", "Quarterly report", "--media", "A4",
            "--sides", options["sides"],
        ])
    expected.extend(["--copies", str(options.get("copies", 1))])
    assert run.call_args.args[0] == expected
    assert run.call_args.kwargs["timeout"] == main.TIMEOUT_SECS
    assert run.call_args.kwargs["stdin"] is main.subprocess.DEVNULL
    assert result == {"job_id": "office-1"}


@pytest.mark.parametrize("confirm", [False, None, 0, 1, "true"])
def test_cancel_requires_confirmation_before_policy(confirm):
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="requires confirmation"):
            main.cancel("office-1", confirm)
    require.assert_not_called()


def test_cancel_uses_control_scope_and_confirm_flag(invoke):
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess, "run", return_value=_completed({"cancelled": True})
    ) as run:
        result = invoke("cancel", job_id="office-1", confirm=True)
    require.assert_called_once_with("device.printer", name="control")
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos",
        "__printer",
        "cancel",
        "--job-id",
        "office-1",
        "--confirm",
    ]
    assert result == {"cancelled": True}


@pytest.mark.parametrize("printer", [None, "", "-office", "office queue", "bad\nname"])
def test_invalid_printer_is_rejected_before_policy(printer):
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="invalid printer name"):
            main.capabilities(printer)
    require.assert_not_called()


@pytest.mark.parametrize("job_id", [None, "", "office", "office-x", "office-1\n"])
def test_invalid_job_id_is_rejected_before_policy(job_id):
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="invalid print job ID"):
            main.cancel(job_id, True)
    require.assert_not_called()


@pytest.mark.parametrize(
    "source",
    [None, "", "relative.pdf", "/home/user/../user/document.pdf", "bad\x00path"],
)
def test_invalid_source_is_rejected_before_policy(source):
    with mock.patch.object(
        main.os.path, "realpath", side_effect=lambda value: main.os.path.normpath(value)
    ), mock.patch.object(main.os.path, "islink", return_value=False), mock.patch.object(
        main.policy, "require"
    ) as require:
        with pytest.raises(ValueError, match="canonical non-symlink path"):
            main.print_document("office", source)
    require.assert_not_called()


def test_symlink_source_is_rejected_before_policy():
    with mock.patch.object(
        main.os.path, "realpath", side_effect=lambda value: value
    ), mock.patch.object(main.os.path, "islink", return_value=True), mock.patch.object(
        main.policy, "require"
    ) as require:
        with pytest.raises(ValueError, match="canonical non-symlink path"):
            main.print_document("office", "/home/user/document.pdf")
    require.assert_not_called()


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"copies": True}, "copies must be an integer"),
        ({"copies": 0}, "copies must be an integer"),
        ({"copies": 101}, "copies must be an integer"),
        ({"title": ""}, "invalid print title"),
        ({"title": "bad\nname"}, "invalid print title"),
        ({"media": "A4 value"}, "invalid media option"),
        ({"sides": "two-sided"}, "invalid sides option"),
    ],
)
def test_invalid_print_options_are_rejected_before_policy(options, message):
    with mock.patch.object(
        main.os.path, "realpath", side_effect=lambda value: value
    ), mock.patch.object(main.os.path, "islink", return_value=False), mock.patch.object(
        main.policy, "require"
    ) as require:
        with pytest.raises(ValueError, match=message):
            main.print_document("office", "/home/user/document.pdf", **options)
    require.assert_not_called()


@pytest.mark.parametrize(
    ("returncode", "stdout", "message"),
    [
        (0, "{", "Printer Manager broker returned invalid JSON"),
        (0, "[]", "Printer Manager broker returned a non-object result"),
        (
            0,
            json.dumps({"error": None}),
            "Printer Manager broker returned an invalid error payload",
        ),
        (0, json.dumps({"error": "CUPS unavailable"}), "CUPS unavailable"),
        (7, "{}", "Printer Manager broker exited 7"),
        (9, json.dumps({"error": "printer denied"}), "printer denied"),
    ],
)
def test_broker_payload_failures_raise(returncode, stdout, message):
    completed = mock.Mock(returncode=returncode, stdout=stdout, stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ), mock.patch.object(main.subprocess, "run", return_value=completed):
        with pytest.raises(RuntimeError, match=message):
            main.status()


def test_missing_broker_executable_raises():
    with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
        main.shutil, "which", return_value=None
    ), mock.patch.object(main.policy, "require"):
        with pytest.raises(FileNotFoundError, match="cos binary not found"):
            main.status()


@pytest.mark.parametrize(
    ("error", "exception", "message"),
    [
        (
            FileNotFoundError("missing"),
            FileNotFoundError,
            "Printer Manager broker executable not found",
        ),
        (
            PermissionError("denied"),
            PermissionError,
            "permission denied launching Printer Manager broker",
        ),
    ],
)
def test_broker_launch_failures_raise(error, exception, message):
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ), mock.patch.object(main.subprocess, "run", side_effect=error):
        with pytest.raises(exception, match=message):
            main.status()


def test_broker_timeout_raises():
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ), mock.patch.object(
        main.subprocess,
        "run",
        side_effect=main.subprocess.TimeoutExpired(["cos"], main.TIMEOUT_SECS),
    ):
        with pytest.raises(
            TimeoutError,
            match=rf"Printer Manager broker exceeded {main.TIMEOUT_SECS}s for status",
        ):
            main.status()
