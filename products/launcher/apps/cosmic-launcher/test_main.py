"""Native identity contracts exercise the same embedded backend and SDK."""

import json
import os
from pathlib import Path
from unittest import mock

import pytest

from test_support import authenticated_mcp_params, load_local_module

PRODUCT = Path(__file__).resolve().parents[2]
NATIVE = PRODUCT / "native/cosmic-launcher"
MANIFEST = Path(__file__).with_name("app.json")


@pytest.fixture
def service(monkeypatch, tmp_path):
    monkeypatch.setenv("COS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("COS_APP_MANIFEST", str(MANIFEST))
    backend = load_local_module(
        PRODUCT / "apps/launcher/main.py", "native_launcher_backend",
        clear_modules=("_shared",),
    )
    exec(compile((NATIVE / "mcp_server.py").read_text(), "<native-mcp>", "exec"),
         backend.__dict__)
    return backend


def call(service, tool, arguments):
    return service.app._handle_request(
        "tools/call",
        authenticated_mcp_params({"name": f"launcher.{tool}", "arguments": arguments}),
        True,
    )


def test_native_manifest_and_install_identity(service):
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["id"] == "cosmic-launcher"
    assert manifest["runtime"] == "binary"
    assert manifest["mcp"]["entry"] == "/usr/bin/cosmic-launcher"
    tools = service.app._handle_request("tools/list", {}, True)["tools"]
    assert {tool["name"] for tool in tools} == {
        "launcher.find", "launcher.list", "launcher.open", "launcher.recent",
    }
    assert next(tool for tool in manifest["mcp"]["tools"]
                if tool["name"] == "launcher.recent")["needs"] == []


@pytest.mark.parametrize("tool,args", [
    ("find", {"query": "editor"}), ("list", {}), ("open", {"app_id": "Editor"}),
    ("recent", {}),
])
def test_all_native_tools_require_authenticated_context(service, tool, args):
    with pytest.raises(Exception, match="missing authenticated"):
        service.app._handle_request(
            "tools/call", {"name": f"launcher.{tool}", "arguments": args}, True,
        )


@pytest.mark.parametrize("value,expected", [(-4, 1), (0, 1), (10, 10), (99, 50)])
def test_find_contract_clamps_limit(service, value, expected):
    with mock.patch.object(service, "find", return_value={"matches": []}) as find:
        assert not call(service, "find", {"query": "Editor", "limit": value}).get("isError")
    find.assert_called_once_with("Editor", expected)


def test_list_preserves_hidden_and_recent_limits(service):
    with mock.patch.object(service, "list_apps", return_value={}) as listing:
        call(service, "list", {"include_hidden": True})
    listing.assert_called_once_with(include_hidden=True)
    with mock.patch.object(service, "recent", return_value={}) as recent:
        call(service, "recent", {"limit": 1000})
    recent.assert_called_once_with(200)


@pytest.mark.parametrize("extras", [["--unsafe"], ["file:///etc/passwd"],
                                    ["/x/../y"], ["https://x/\n"], [42]])
def test_extras_invalid_before_policy_or_launch(service, extras):
    with mock.patch.object(service.policy, "require") as require, mock.patch.object(
        service, "_broker_launch",
    ) as launch:
        assert call(service, "open", {"app_id": "Editor", "extras": extras})["isError"]
    require.assert_not_called()
    launch.assert_not_called()


def test_ordered_targets_exact_authority_and_separate_history(service, tmp_path):
    document = tmp_path / "doc.txt"
    document.write_text("fixture")
    payload = {"launched": True, "app_id": "Editor", "launcher": "/usr/bin/gtk4-launch"}
    with mock.patch.object(service, "_find_entry", return_value={"name": "Editor"}), \
            mock.patch.object(service.policy, "require") as require, \
            mock.patch.object(service, "_broker_launch", return_value=payload) as launch:
        response = call(service, "open", {
            "app_id": "Editor", "extras": ["https://before", str(document), "https://after"],
        })
    assert not response.get("isError")
    launch.assert_called_once_with(
        "Editor", ["https://before", document.as_uri(), "https://after"],
    )
    assert require.call_args_list == [
        mock.call("fs.read", path=str(document)), mock.call("desktop.launch", name="Editor"),
    ]
    assert Path(service.RECENT_PATH).is_relative_to(Path(os.environ["COS_DATA_DIR"]))
    assert call(service, "recent", {})["structuredContent"]["recent"][0]["app_id"] == "Editor"


def test_catalog_denied_before_reading_entries(service, tmp_path):
    root = tmp_path / "applications"
    root.mkdir()
    with mock.patch.object(service, "_xdg_data_dirs", return_value=[str(root)]), \
            mock.patch.object(service.policy, "require", side_effect=PermissionError("denied")), \
            mock.patch.object(service.os, "walk") as walk:
        assert call(service, "list", {})["isError"]
    walk.assert_not_called()


def test_launch_denied_and_broker_errors_do_not_record_history(service):
    with mock.patch.object(service, "_find_entry", return_value={"name": "Editor"}), \
            mock.patch.object(service.policy, "require", side_effect=PermissionError("denied")), \
            mock.patch.object(service, "_broker_launch") as launch:
        assert call(service, "open", {"app_id": "Editor"})["isError"]
    launch.assert_not_called()
    assert not Path(service.RECENT_PATH).exists()
    with mock.patch.object(service, "_find_entry", return_value={"name": "Editor"}), \
            mock.patch.object(service.policy, "require"), \
            mock.patch.object(service, "_broker_launch", side_effect=RuntimeError("broker failed")):
        assert call(service, "open", {"app_id": "Editor"})["isError"]
    assert not Path(service.RECENT_PATH).exists()


def test_staged_native_embeds_canonical_product_source(tmp_path):
    stage = load_local_module(PRODUCT.parents[1] / "tools/stage_native.py",
                              "launcher_stage_native")
    assert stage.stage("launcher", tmp_path) == ["cosmic-launcher"]
    staged = tmp_path / "cosmic-launcher"
    assert (staged / "mcp_backend.py").read_bytes() == (
        PRODUCT / "apps/launcher/main.py"
    ).read_bytes()
    assert (staged / "LICENSE.md").is_file()
    assert (staged / "data/com.clawos.Launcher.desktop").is_file()
    assert '"app", "launcher"' not in (staged / "src/mcp.rs").read_text()


def test_native_asset_cannot_escape_product_or_destination(tmp_path):
    stage = load_local_module(PRODUCT.parents[1] / "tools/stage_native.py",
                              "launcher_asset_stager")
    for assets in ({"../escape": "apps/launcher/main.py"}, {"valid": "../other/main.py"}):
        with pytest.raises(ValueError, match="Native asset"):
            stage.stage_assets(PRODUCT, {"native_assets": {"launcher": assets}},
                               "launcher", tmp_path)
