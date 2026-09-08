import json
import os
import pathlib
import sys
from unittest import mock

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(
    pathlib.Path(__file__).with_name("main.py"),
    "claw_test_clipboard_manager_main",
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
            pathlib.Path(__file__).with_name("server.py"), "claw_test_clipboard_manager_server",
        )
        listed = server.app._handle_request("tools/list", {}, True)
        assert {tool["name"] for tool in listed["tools"]} == {
            f"clipboard-manager.{name}" for name in ["status", "types", "read", "write", "clear"]
        }

        def call(command, **arguments):
            if request.param == "direct":
                function = main.list_types if command == "types" else getattr(main, command)
                return function(**arguments)
            response = server.app._handle_request(
                "tools/call",
                authenticated_mcp_params({
                    "name": f"clipboard-manager.{command}", "arguments": arguments,
                }),
                True,
            )
            return response["structuredContent"]

        yield call


def test_manifest_keeps_selection_scopes_source_read_and_confirmation():
    manifest = json.loads(pathlib.Path(__file__).with_name("app.json").read_text())
    assert "operations" not in manifest
    for tool in manifest["mcp"]["tools"]:
        command = tool["name"].removeprefix("clipboard-manager.")
        verb = "clipboard.write" if command in ("write", "clear") else "clipboard.read"
        expected = [(verb, {"kind": "fixed", "scope": {"kind": "name", "value": "selection"}})]
        if command == "write":
            expected.append(("fs.read", {"kind": "from-arg", "arg": "source"}))
        assert [(need["verb"], need["scope"]) for need in tool["needs"]] == expected
        args = {arg["name"]: arg for arg in tool["args"]}
        assert args["primary"]["default"] is False
        if command == "clear":
            assert args["confirm"]["required"] is True
            assert args["confirm"]["choices"] == [True]


def _completed(payload: object, returncode: int = 0) -> mock.Mock:
    return mock.Mock(
        returncode=returncode,
        stdout=json.dumps(payload),
        stderr="",
    )


def test_status_uses_sensitive_clipboard_scope_and_selection(invoke):
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess, "run", return_value=_completed({"types": []})
    ) as run:
        result = invoke("status", primary=True)
    require.assert_called_once_with("clipboard.read", name="selection")
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos",
        "__clipboard",
        "status",
        "--primary",
    ]
    assert result == {"types": []}


def test_types_uses_sensitive_clipboard_scope(invoke):
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess, "run", return_value=_completed({"types": ["text/plain"]})
    ) as run:
        result = invoke("types")
    require.assert_called_once_with("clipboard.read", name="selection")
    assert run.call_args.args[0] == ["/usr/local/bin/cos", "__clipboard", "types"]
    assert result == {"types": ["text/plain"]}


def test_read_uses_sensitive_clipboard_scope_and_mime(invoke):
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess, "run", return_value=_completed({"text": "hello"})
    ) as run:
        result = invoke("read", mime="text/plain")
    require.assert_called_once_with("clipboard.read", name="selection")
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos",
        "__clipboard",
        "read",
        "--mime",
        "text/plain",
    ]
    assert result == {"text": "hello"}


def test_write_uses_clipboard_and_source_scopes(invoke):
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.os.path, "realpath", side_effect=lambda value: value
    ), mock.patch.object(main.os.path, "islink", return_value=False), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess, "run", return_value=_completed({"written": True})
    ) as run:
        result = invoke("write", source="/home/user/clip.txt", mime="text/plain", primary=True)
    assert require.call_args_list == [
        mock.call("clipboard.write", name="selection"),
        mock.call("fs.read", path="/home/user/clip.txt"),
    ]
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos",
        "__clipboard",
        "write",
        "--mime",
        "text/plain",
        "--source",
        "/home/user/clip.txt",
        "--primary",
    ]
    assert run.call_args.kwargs["timeout"] == main.TIMEOUT_SECS
    assert run.call_args.kwargs["stdin"] is main.subprocess.DEVNULL
    assert result == {"written": True}


@pytest.mark.parametrize("confirm", [False, None, 0, 1, "true"])
def test_clear_requires_confirmation_before_policy(confirm):
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="requires confirmation"):
            main.clear(confirm)
    require.assert_not_called()


def test_clear_uses_clipboard_scope_and_confirm_flag(invoke):
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess, "run", return_value=_completed({"cleared": True})
    ) as run:
        result = invoke("clear", confirm=True, primary=True)
    require.assert_called_once_with("clipboard.write", name="selection")
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos",
        "__clipboard",
        "clear",
        "--primary",
        "--confirm",
    ]
    assert result == {"cleared": True}


@pytest.mark.parametrize("command", ["status", "types", "read", "write", "clear"])
@pytest.mark.parametrize("primary", [None, False, True])
def test_selection_defaults_and_omitted_mime(invoke, tmp_path, command, primary):
    source = tmp_path / "clipboard.bin"
    source.write_bytes(b"fixture")
    arguments = {}
    flags = []
    if command == "write":
        arguments["source"] = str(source)
        flags += ["--source", str(source)]
    if primary is not None:
        arguments["primary"] = primary
    if primary:
        flags.append("--primary")
    if command == "clear":
        arguments["confirm"] = True
        flags.append("--confirm")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=_completed({"ok": True})) as run:
        assert invoke(command, **arguments) == {"ok": True}
    verb = "clipboard.write" if command in ("write", "clear") else "clipboard.read"
    expected = [mock.call(verb, name="selection")]
    if command == "write":
        expected.append(mock.call("fs.read", path=str(source)))
    assert require.call_args_list == expected
    assert run.call_args.args[0] == ["/usr/local/bin/cos", "__clipboard", command, *flags]
    assert run.call_args.kwargs["timeout"] == main.TIMEOUT_SECS
    assert run.call_args.kwargs["stdin"] is main.subprocess.DEVNULL


@pytest.mark.parametrize("primary", [None, 0, 1, "true"])
def test_invalid_selection_is_rejected_before_policy(primary):
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="primary must be a boolean"):
            main.status(primary)
    require.assert_not_called()


@pytest.mark.parametrize(
    "mime",
    [42, "", "text", "-text/plain", "text/plain value", "a/" + "b" * 254],
)
def test_invalid_mime_is_rejected_before_policy(mime):
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="invalid MIME type"):
            main.read(mime)
    require.assert_not_called()


@pytest.mark.parametrize(
    "source",
    [None, "", "relative.txt", "/home/user/../user/clip.txt", "bad\x00path"],
)
def test_invalid_source_is_rejected_before_policy(source):
    with mock.patch.object(
        main.os.path, "realpath", side_effect=lambda value: main.os.path.normpath(value)
    ), mock.patch.object(main.os.path, "islink", return_value=False), mock.patch.object(
        main.policy, "require"
    ) as require:
        with pytest.raises(ValueError, match="canonical non-symlink path"):
            main.write(source)
    require.assert_not_called()


def test_symlink_source_is_rejected_before_policy():
    with mock.patch.object(
        main.os.path, "realpath", side_effect=lambda value: value
    ), mock.patch.object(main.os.path, "islink", return_value=True), mock.patch.object(
        main.policy, "require"
    ) as require:
        with pytest.raises(ValueError, match="canonical non-symlink path"):
            main.write("/home/user/clip.txt")
    require.assert_not_called()


@pytest.mark.parametrize(
    ("returncode", "stdout", "message"),
    [
        (0, "{", "Clipboard Manager broker returned invalid JSON"),
        (0, "[]", "Clipboard Manager broker returned a non-object result"),
        (0, json.dumps({"error": ""}), "invalid error payload"),
        (0, json.dumps({"error": "clipboard unavailable"}), "clipboard unavailable"),
        (7, "{}", "Clipboard Manager broker exited 7"),
        (9, json.dumps({"error": "clipboard denied"}), "clipboard denied"),
    ],
)
def test_broker_payload_failures_raise(returncode, stdout, message):
    completed = mock.Mock(returncode=returncode, stdout=stdout, stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed):
        with pytest.raises(RuntimeError, match=message):
            main.status()
    require.assert_called_once_with("clipboard.read", name="selection")


def test_missing_broker_executable_raises():
    with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
        main.shutil, "which", return_value=None
    ), mock.patch.object(main.policy, "require") as require:
        with pytest.raises(FileNotFoundError, match="cos binary not found"):
            main.status()
    require.assert_called_once_with("clipboard.read", name="selection")


@pytest.mark.parametrize(
    ("error", "exception", "message"),
    [
        (
            FileNotFoundError("missing"),
            FileNotFoundError,
            "Clipboard Manager broker executable not found",
        ),
        (
            PermissionError("denied"),
            PermissionError,
            "permission denied launching Clipboard Manager broker",
        ),
    ],
)
def test_broker_launch_failures_raise(error, exception, message):
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", side_effect=error):
        with pytest.raises(exception, match=message):
            main.status()
    require.assert_called_once_with("clipboard.read", name="selection")


def test_broker_timeout_raises():
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess,
        "run",
        side_effect=main.subprocess.TimeoutExpired(["cos"], main.TIMEOUT_SECS),
    ):
        with pytest.raises(TimeoutError, match="Clipboard Manager broker exceeded"):
            main.status()
    require.assert_called_once_with("clipboard.read", name="selection")
