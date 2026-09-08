"""Product packaging must keep the established installed App contract."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("app_stage", ROOT / "tools" / "stage.py")
stage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage)


def test_calendar_stage_is_separate_and_preserves_its_manifest(tmp_path):
    assert {"mail", "calendar"} <= set(stage.products())
    assert stage.stage("calendar", tmp_path) == ["calendar", "panel-calendar"]
    app = tmp_path / "usr/lib/cos/apps/calendar"
    source = ROOT / "products/calendar/apps/calendar"
    assert (app / "app.json").read_bytes() == (source / "app.json").read_bytes()
    assert (app / "main.py").read_bytes() == (source / "main.py").read_bytes()
    assert (app / "server.py").is_file()
    assert not (app / "test_main.py").exists()
    assert not (tmp_path / "usr/lib/cos/apps/mail-ai").exists()


def test_files_stage_preserves_the_direct_mcp_contract(tmp_path):
    assert "files" in stage.products()
    assert stage.stage("files", tmp_path) == ["fs", "docs"]
    for app_id in ("fs", "docs"):
        app = tmp_path / "usr/lib/cos/apps" / app_id
        source = ROOT / "products/files/apps" / app_id
        for filename in ("app.json", "main.py", "server.py"):
            assert (app / filename).read_bytes() == (source / filename).read_bytes()
        assert not (app / "test_main.py").exists()
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "usr/lib/systemd").exists()


def test_browser_stage_preserves_search_without_os_services(tmp_path):
    assert "browser" in stage.products()
    assert stage.stage("browser", tmp_path) == ["search", "web", "browser-attached"]
    for app_id in ("search", "web", "browser-attached"):
        app = tmp_path / "usr/lib/cos/apps" / app_id
        source = ROOT / "products/browser/apps" / app_id
        for filename in ("app.json", "main.py", "server.py"):
            assert (app / filename).read_bytes() == (source / filename).read_bytes()
        assert not (app / "test_main.py").exists()
    native_host = "usr/lib/cos/apps/browser-attached/native_host.py"
    assert (tmp_path / native_host).read_bytes() == (
        ROOT / "products/browser/apps/browser-attached/native_host.py"
    ).read_bytes()
    assert not (tmp_path / "usr/lib/cos/apps/_shared").exists()
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "usr/bin/cos-browser").exists()
    assert not (tmp_path / "etc/chromium").exists()


def test_terminal_stage_preserves_exec_without_process_services(tmp_path):
    assert "terminal" in stage.products()
    assert stage.stage("terminal", tmp_path) == ["exec"]
    app = tmp_path / "usr/lib/cos/apps/exec"
    source = ROOT / "products/terminal/apps/exec"
    for filename in ("app.json", "main.py", "server.py"):
        assert (app / filename).read_bytes() == (source / filename).read_bytes()
    assert not (app / "test_main.py").exists()
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "var/lib/cos").exists()


@pytest.mark.parametrize(("product", "app_ids"), [
    ("containers", ["container-manager"]),
    ("backup-recovery", ["backup-center", "system-snapshot"]),
    ("store", ["pkg"]),
    ("diagnostics", ["hardware-center", "crash-doctor", "netdiag"]),
    ("storage", ["storage-manager"]),
    ("security", ["security-center", "firewall-manager", "usb-guard"]),
    ("maintenance", ["config-editor", "systemd"]),
    ("events-audit", ["event-center", "log"]),
    ("launcher", ["launcher", "cosmic-launcher"]),
    ("clipboard", ["clipboard-manager", "panel-clipboard"]),
    ("settings", ["accessibility-manager", "audio-manager", "bluetooth-manager", "camera-manager", "display-manager", "desktop-manager", "location-manager", "network-manager", "power-manager", "printer-manager", "user-manager"]),
])
def test_broker_products_stage_without_os_services(tmp_path, product, app_ids):
    assert product in stage.products()
    assert stage.stage(product, tmp_path) == app_ids
    for app_id in app_ids:
        app = tmp_path / "usr/lib/cos/apps" / app_id
        source = ROOT / "products" / product / "apps" / app_id
        filenames = (("app.json",) if app_id == "cosmic-launcher" else
                     ("app.json", "main.sh") if app_id == "panel-clipboard" else
                     ("app.json", "main.py", "server.py"))
        for filename in filenames:
            assert (app / filename).read_bytes() == (source / filename).read_bytes()
        assert not (app / "test_main.py").exists()
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "usr/bin").exists()
    assert not (tmp_path / "var/lib").exists()


def test_mail_stage_contains_matching_app_and_ui_without_os_runtime(tmp_path):
    assert stage.stage("mail", tmp_path) == ["mail-ai", "email", "gateway-email"]
    app = tmp_path / "usr/lib/cos/apps/mail-ai"
    assert (app / "server.py").is_file()
    assert (app / "native_host.py").is_file()
    assert not (app / "test_main.py").exists()
    email = tmp_path / "usr/lib/cos/apps/email"
    assert (email / "main.py").is_file()
    assert (email / "server.py").is_file()
    assert not (email / "test_main.py").exists()
    assert not (tmp_path / "usr/lib/cos/apps/_shared").exists()
    gateway = tmp_path / "usr/lib/cos/apps/gateway/email"
    assert (gateway / "main.py").is_file()
    assert (gateway / "server.py").is_file()
    assert not (gateway / "test_main.py").exists()
    assert not (tmp_path / "usr/lib/cos/apps/gateway-email").exists()
    assert not (tmp_path / "usr/lib/cos/apps/gateway/_shared").exists()
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "usr/lib/cos/claw-mail-ai-host").exists()
    manifest = json.loads((app / "app.json").read_text())
    xpi = tmp_path / "usr/lib/thunderbird/distribution/extensions/claw-mail-ai@claw.os.xpi"
    with zipfile.ZipFile(xpi) as archive:
        assert json.loads(archive.read("manifest.json"))["version"] == manifest["version"]
        assert "test_contract.py" not in archive.namelist()
    with pytest.raises(FileExistsError):
        stage.stage("mail", tmp_path)


def test_home_integration_stages_only_adapter_payload(tmp_path):
    assert stage.stage("home-integration", tmp_path) == ["gateway-homeassistant"]
    source = ROOT / "products/home-integration/apps/gateway/homeassistant"
    installed = tmp_path / "usr/lib/cos/apps/gateway/homeassistant"
    assert {path.name for path in installed.iterdir()} == {"app.json", "main.py", "server.py"}
    for filename in ("app.json", "main.py", "server.py"):
        assert (installed / filename).read_bytes() == (source / filename).read_bytes()
    assert not (tmp_path / "usr/lib/cos/apps/gateway-homeassistant").exists()
    assert not (tmp_path / "usr/lib/cos/apps/gateway/_shared").exists()
    assert not (tmp_path / "var/lib").exists()


def test_notification_delivery_stages_only_product_payload(tmp_path):
    assert stage.stage("notification-delivery", tmp_path) == ["gateway-ntfy", "gateway-pushover", "gateway-webhook"]
    for channel in ("ntfy", "pushover", "webhook"):
        source = ROOT / "products/notification-delivery/apps/gateway" / channel
        installed = tmp_path / "usr/lib/cos/apps/gateway" / channel
        assert {path.name for path in installed.iterdir()} == {"app.json", "main.py", "server.py"}
        for filename in ("app.json", "main.py", "server.py"):
            assert (installed / filename).read_bytes() == (source / filename).read_bytes()
        assert not (tmp_path / "usr/lib/cos/apps" / f"gateway-{channel}").exists()
    assert not (tmp_path / "usr/lib/cos/apps/gateway/_shared").exists()
    assert not (tmp_path / "var/lib").exists()


def test_messaging_channels_stage_nested_connector_without_shared_runtime_or_state(tmp_path):
    assert stage.stage("messaging-channels", tmp_path) == ["gateway-discord", "gateway-dingtalk", "gateway-googlechat", "gateway-larksuite", "gateway-matrix", "gateway-mattermost", "gateway-rocketchat", "gateway-signal", "gateway-slack", "gateway-sms", "gateway-teams", "gateway-telegram", "gateway-webex", "gateway-whatsapp", "gateway-zulip"]
    for channel in ("discord", "dingtalk", "googlechat", "larksuite", "matrix", "mattermost", "rocketchat", "signal", "slack", "sms", "teams", "telegram", "webex", "whatsapp", "zulip"):
        source = ROOT / "products/messaging-channels/apps/gateway" / channel
        installed = tmp_path / "usr/lib/cos/apps/gateway" / channel
        for filename in ("app.json", "main.py", "server.py"):
            assert (installed / filename).read_bytes() == (source / filename).read_bytes()
        assert not (installed / "test_main.py").exists()
        assert not (tmp_path / "usr/lib/cos/apps" / f"gateway-{channel}").exists()
    assert not (tmp_path / "usr/lib/cos/apps/gateway/_shared").exists()
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "var/lib").exists()


@pytest.mark.parametrize("layout,app_id", [
    ("apps/gateway/email", "email"),
    ("apps/../outside", "outside"),
    ("apps", "mail"),
])
def test_stage_rejects_identity_or_layout_drift(tmp_path, monkeypatch, layout, app_id):
    source = tmp_path / "source"
    product = source / "products/mail"
    product.mkdir(parents=True)
    (product / "package.json").write_text(json.dumps({"apps": [layout]}))
    if layout == "apps/gateway/email":
        app = product / layout
        app.mkdir(parents=True)
        (app / "app.json").write_text(json.dumps({"id": app_id}))
    monkeypatch.setattr(stage, "ROOT", source)
    target = tmp_path / "stage"
    with pytest.raises(ValueError, match="layout"):
        stage.stage("mail", target)
    assert not target.exists()


def test_packaged_gateway_runs_with_only_installed_libraries(tmp_path):
    stage.stage("mail", tmp_path)
    lock = json.loads((ROOT / "platform.lock.json").read_text())
    platform = ROOT / "build/platform" / lock["revision"]
    python = tmp_path / "usr/lib/cos/python"
    python.mkdir()
    for source in lock["python_sources"]:
        shutil.copytree(platform / source, python, dirs_exist_ok=True)
    shutil.copy2(platform / "apps/canonical_argv.py", python / "canonical_argv.py")
    apps = tmp_path / "usr/lib/cos/apps"
    shutil.copytree(platform / "apps/gateway/_shared", apps / "gateway/_shared")
    result = subprocess.run(
        [sys.executable, str(apps / "gateway/email/main.py"), "status"],
        cwd=tmp_path, capture_output=True, text=True, check=True, timeout=20,
        env={
            "PATH": os.defpath, "PYTHONPATH": str(python),
            "COS_SMTP_HOST": "smtp.example.invalid", "COS_SMTP_PORT": "587",
            "COS_SMTP_USER": "fixture@example.invalid", "COS_SMTP_PASSWORD": "fixture",
            "COS_SMTP_FROM": "fixture@example.invalid",
        },
    )
    status = json.loads(result.stdout)
    assert status["configured"] is True
    assert status["platform"] == "email"
    assert status["tls"] == "starttls"
