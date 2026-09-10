import json
import stat
import sys

import pytest

import release
import release_payload
import release_publish
from release_common import config, package_record


@pytest.mark.parametrize(("name", "architecture"), [
    ("claw-app-calendar-desktop", "amd64"),
    ("claw-app-independent-example", "all"),
])
@pytest.mark.parametrize("hook", ["preinst", "postinst", "prerm", "postrm", "config", "triggers"])
def test_no_origin_or_package_variant_can_supply_root_hooks(deb, name, architecture, hook):
    content = b"interest-noawait fixture-event\n" if hook == "triggers" else b"#!/bin/sh\nexit 0\n"
    package = deb(name, architecture=architecture, control_files={hook: content},
                  modes={f"DEBIAN/{hook}": 0o644 if hook == "triggers" else 0o755})
    with pytest.raises(ValueError, match="maintainer/root hooks"):
        package_record(package)


@pytest.mark.parametrize("path", [
    "var/lib/cos/owners/1000/grants.json",
    "etc/sudoers.d/app-fixture",
    "usr/lib/systemd/system/app-fixture.service",
    "usr/lib/systemd/system-generators/app-fixture",
    "usr/share/dbus-1/system-services/app-fixture.service",
    "usr/share/polkit-1/rules.d/app-fixture.rules",
    "usr/lib/sysusers.d/app-fixture.conf",
    "usr/lib/tmpfiles.d/app-fixture.conf",
    "usr/lib/udev/rules.d/app-fixture.rules",
    "usr/lib/apt/methods/app-fixture",
])
def test_app_packages_cannot_install_authority_configuration_or_owner_state(deb, path):
    package = deb(files={path: b"fixture only\n"})
    with pytest.raises(ValueError, match="state, grants or OS authority"):
        package_record(package)


def test_app_asset_symlink_cannot_redirect_to_authority_configuration(deb):
    package = deb(symlinks={
        "usr/share/app-fixture/alias": "../polkit-1/actions/app-fixture.policy",
    })
    with pytest.raises(ValueError, match="OS authority"):
        package_record(package)


def test_settings_package_origin_does_not_exempt_polkit_configuration(deb):
    package = deb("claw-app-settings-desktop", architecture="amd64", files={
        "usr/share/polkit-1/rules.d/cosmic-settings.rules": b"fixture only\n",
        "usr/share/polkit-1/actions/com.clawos.Settings.Users.policy": b"fixture only\n",
    })
    with pytest.raises(ValueError, match="OS authority"):
        package_record(package)


@pytest.mark.parametrize("mode", [0o4755, 0o2755])
def test_debian_payload_cannot_confer_setuid_or_setgid_privilege(deb, mode):
    package = deb(files={"usr/bin/app-fixture": b"fixture only\n"}, modes={"usr/bin/app-fixture": mode})
    with pytest.raises(ValueError, match="privilege-bearing"):
        package_record(package)


def test_normalization_rejects_instead_of_silently_stripping_app_privilege(tmp_path, monkeypatch):
    root = tmp_path / "stage"
    binary = root / "usr/bin/app-fixture"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"fixture only\n")
    binary.chmod(0o4755)
    with pytest.raises(ValueError, match="setuid"):
        release.normalize(root, 1700000000)
    assert binary.stat().st_mode & stat.S_ISUID
    binary.chmod(0o755)
    monkeypatch.setattr(release_payload.os, "listxattr", lambda *args, **kwargs: ["security.capability"])
    with pytest.raises(ValueError, match="file capabilities"):
        release.normalize(root, 1700000000)


def test_app_installer_cannot_create_debian_metadata(tmp_path):
    root = tmp_path / "stage"
    (root / "DEBIAN").mkdir(parents=True)
    (root / "DEBIAN/postinst").write_text("fixture only\n")
    with pytest.raises(ValueError, match="App installer cannot"):
        release_payload.validate_install_tree(root, allow_control=False)


@pytest.mark.parametrize(("name", "architecture", "runtime"), [
    ("claw-app-calendar-desktop", "amd64", "binary"),
    ("claw-app-independent-example", "all", "python"),
])
def test_manifest_needs_remain_declarations_not_installed_grants(deb, name, architecture, runtime):
    manifest = json.dumps({
        "id": "example", "runtime": runtime,
        "mcp": {"tools": [{"name": "example.read", "needs": [{"verb": "fs.read", "scope": {"kind": "wild"}}]}]},
    }).encode()
    package = deb(name, architecture=architecture, files={
        "usr/lib/cos/apps/example/app.json": manifest,
        "usr/share/doc/app-fixture/copyright": b"fixture only\n",
    })
    record = package_record(package)
    assert record["package"] == name
    assert not any("grant" in field.lower() or "trusted" in field.lower() for field in record["control"])


def test_publication_requires_generic_contract_review_and_has_no_environment_override(monkeypatch):
    monkeypatch.setenv("CLAW_APPS_INTEGRATION_APPROVED", "1")
    with pytest.raises(ValueError, match="generic authenticated App Host"):
        release_publish.require_publication_contract(config())
    release_publish.require_publication_contract({"integration_contract": "verified-origin-neutral-app-host"})
    with pytest.raises(ValueError, match="blocked"):
        release_publish.require_publication_contract({})


def test_pending_integration_stops_publication_before_github_or_signing(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", [
        "release_publish.py", "publish", "--plan", str(tmp_path / "not-read"),
        "--artifacts", str(tmp_path / "not-read"),
    ])
    monkeypatch.setattr(release_publish, "GitHub", lambda: pytest.fail("pending contract must not contact GitHub"))
    with pytest.raises(ValueError, match="publication is blocked"):
        release_publish.main()
