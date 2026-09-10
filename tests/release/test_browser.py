import copy
import json
from pathlib import Path
import shutil
import sys
import tarfile

import pytest

from package_assets import asset_entries, stage_assets
import release
from release_apt import compose
from release_common import ROOT, digest, fields, run
from release_development import build_archive, verify_archive
from test_apt import IsolatedApt
from test_packages import contents


EXTENSION = Path("usr/share/claw/extensions/claw-agent-browser")
LAUNCHER = Path("usr/lib/cos/claw-browser-host")
HOST = Path("usr/lib/cos/apps/browser-attached/native_host.py")
RESOURCES = {"manifest.json", "background.js", "content.js", "popup.html", "popup.js", "README.md"}
HOST_COMMAND = '#!/bin/sh\nexec /usr/bin/python3 /usr/lib/cos/apps/browser-attached/native_host.py "$@"\n'


@pytest.fixture
def browser_source(tmp_path, monkeypatch):
    source = tmp_path / "source/products/browser"
    shutil.copytree(ROOT / "products/browser", source, symlinks=True)
    monkeypatch.setattr(release.stage, "ROOT", tmp_path / "source")
    return source


def test_browser_package_owns_complete_extension_and_the_single_canonical_host(tmp_path):
    plan = release.make_plan("browser", "1.2.3")
    assert [entry["package"] for entry in plan["packages"]] == ["claw-app-browser"]
    assert [job["architecture"] for job in plan["matrix"]["include"]] == ["all"]
    for name in ("first", "second"):
        release.build(plan, "all", tmp_path / name)
    package = tmp_path / "first/claw-app-browser_1.2.3_all.deb"
    assert digest(package) == digest(tmp_path / "second" / package.name)
    entries = contents(package)
    assert {Path(name).relative_to(EXTENSION).as_posix() for name, entry in entries.items()
            if entry.isfile() and Path(name).is_relative_to(EXTENSION)} == RESOURCES
    assert entries[LAUNCHER.as_posix()].mode == 0o755
    assert [name for name in entries if name.endswith("/native_host.py")] == [HOST.as_posix()]
    assert not any(name.startswith(("usr/lib/cos/browser-agent", "usr/share/clawos-app/browser", "etc/", "home/", "var/"))
                   for name in entries)
    assert all(entry.uid == entry.gid == 0 for entry in entries.values())
    payload = tmp_path / "payload"
    run(["dpkg-deb", "--extract", package, payload])
    assert (payload / LAUNCHER).read_text() == HOST_COMMAND
    run(["sh", "-n", payload / LAUNCHER])
    source, declaration = release.stage.load_package("browser")
    assert [(origin.relative_to(source).as_posix(), target.as_posix())
            for origin, target in asset_entries(source, declaration, ["browser-attached"])] == [
        ("extension", EXTENSION.as_posix()), ("packaging/claw-browser-host", LAUNCHER.as_posix()),
    ]
    for resource in RESOURCES:
        assert (payload / EXTENSION / resource).read_bytes() == (source / "extension" / resource).read_bytes()
    assert (payload / HOST).read_bytes() == (source / "apps/browser-attached/native_host.py").read_bytes()
    control = fields(run(["dpkg-deb", "-f", package]).stdout.decode().strip())
    assert control["X-Claw-App-Ids"] == "search, web, browser-attached"
    assert "chromium" not in control["Depends"] and "claw-os-app-permissions-v1" not in control["Depends"]
    assert control["Breaks"] == control["Replaces"] == "claw-os-agent (<< 1:0.3.0)"


def test_browser_fixture_archive_restages_the_declared_extension_and_launcher(tmp_path):
    plan = release.make_plan("browser", "1.2.3")
    record = build_archive(plan, "browser", tmp_path / "archives")
    archive = tmp_path / "archives" / record["filename"]
    manifest = verify_archive(archive, record, plan)
    assert manifest["apps"] == ["search", "web", "browser-attached"]
    assert manifest["asset_helper"] == "tools/package_assets.py"
    root = tmp_path / "fixture"
    with tarfile.open(archive) as stream:
        stream.extractall(root, filter="data")
    assert (root / "tools/package_assets.py").is_file()
    projection = json.loads((root / "products/browser/package.json").read_text())
    assert projection["installed_assets"] == json.loads((ROOT / "products/browser/package.json").read_text())["installed_assets"]
    staged = tmp_path / "staged"
    run([sys.executable, root / "tools/stage.py", "browser", "--apps", "browser-attached",
         "--root", staged], cwd=root, env={"PYTHONDONTWRITEBYTECODE": "1"})
    for relative in (LAUNCHER, HOST, *(EXTENSION / resource for resource in RESOURCES)):
        assert (staged / relative).read_bytes() == (root / "payload" / relative).read_bytes()
    assert (staged / LAUNCHER).stat().st_mode & 0o777 == 0o755
    assert not (staged / EXTENSION / "test_contract.py").exists()
    assert not (staged / "usr/lib/cos/apps/search").exists()


def test_browser_asset_cli_is_separate_from_app_and_common_library_staging(tmp_path):
    command = [sys.executable, ROOT / "tools/package_assets.py", "browser"]
    headless = tmp_path / "search-assets"
    result = run([*command, "--apps", "search", "--root", headless])
    assert json.loads(result.stdout) == [] and not headless.exists()
    attached = tmp_path / "attached-assets"
    result = run([*command, "--apps", "browser-attached", "--root", attached])
    assert json.loads(result.stdout) == [EXTENSION.as_posix(), LAUNCHER.as_posix()]
    assert (attached / LAUNCHER).read_text() == HOST_COMMAND
    assert not (attached / "usr/lib/cos/apps").exists()
    assert not (attached / "usr/lib/cos/python").exists()


def test_real_browser_apt_upgrade_updates_extension_and_host_together_without_registration_or_data_changes(
    tmp_path, browser_source, deb, signing,
):
    release.build(release.make_plan("browser", "1.0.0"), "all", tmp_path / "first")
    platform = [
        deb("claw-app-fixture-platform", extra={
            "Provides": "claw-os-app-runtime-v1, claw-app-support-v1, python3 (= 3.13)",
        }),
        deb("claw-app-unrelated"),
    ]
    repository = compose([*platform, *sorted((tmp_path / "first").glob("*.deb"))],
                         tmp_path / "repository", signing, initialize=True)
    apt = IsolatedApt(tmp_path / "root", repository, signing)
    preserved = {}
    for relative, content in {
        "var/lib/cos/owners/1000/grants.json": b'{"browser-attached":["exact existing grants"]}\n',
        "home/owner/.local/share/claw/apps/browser-attached/state.json": b'{"owner":"unchanged"}\n',
        "home/owner/.config/chromium/Default/Preferences": b'{"profile":"unchanged"}\n',
        "etc/chromium/native-messaging-hosts/com.clawos.browser.json": b'{"allowed_origins":["existing owner registration"]}\n',
        "etc/chromium/policies/managed/claw-browser-agent.json": b'{"policy":"OS owned"}\n',
    }.items():
        path = apt.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(0o600)
        preserved[path] = (content, path.stat().st_mode, path.stat().st_ino)
    apt.update()
    apt.call("install", "-y", "claw-app-browser", "claw-app-unrelated")
    assert apt.installed("claw-app-browser") == "1.0.0"
    original_host = (apt.root / HOST).read_bytes()
    original_background = (apt.root / EXTENSION / "background.js").read_bytes()
    for relative, suffix in (
        ("apps/browser-attached/native_host.py", b"\n# Independent Browser upgrade fixture.\n"),
        ("extension/background.js", b"\n// Independent Browser upgrade fixture.\n"),
    ):
        path = browser_source / relative
        path.write_bytes(path.read_bytes() + suffix)
    release.build(release.make_plan("browser", "1.1.0"), "all", tmp_path / "second")
    updated = compose(sorted((tmp_path / "second").glob("*.deb")), tmp_path / "updated",
                      signing, previous=repository)
    shutil.rmtree(repository)
    updated.rename(repository)
    apt.update()
    apt.call("install", "--only-upgrade", "-y", "claw-app-browser")
    assert apt.installed("claw-app-browser") == "1.1.0"
    assert apt.installed("claw-app-unrelated") == "1.0.0"
    assert (apt.root / HOST).read_bytes() != original_host
    assert (apt.root / EXTENSION / "background.js").read_bytes() != original_background
    assert (apt.root / HOST).read_bytes() == (browser_source / "apps/browser-attached/native_host.py").read_bytes()
    assert (apt.root / LAUNCHER).read_text() == HOST_COMMAND
    assert (apt.root / LAUNCHER).stat().st_mode & 0o777 == 0o755
    for relative in (LAUNCHER, HOST, *(EXTENSION / resource for resource in RESOURCES)):
        owner = run(["dpkg-query", f"--admindir={apt.root}/var/lib/dpkg",
                     "--search", "/" + relative.as_posix()]).stdout.decode().strip()
        assert owner == f"claw-app-browser: /{relative.as_posix()}"
    for resource in RESOURCES:
        assert (apt.root / EXTENSION / resource).read_bytes() == (browser_source / "extension" / resource).read_bytes()
    for path, expected in preserved.items():
        assert (path.read_bytes(), path.stat().st_mode, path.stat().st_ino) == expected
    assert not (apt.root / "usr/lib/cos/browser-agent").exists()
    assert not (apt.root / "usr/share/clawos-app/browser").exists()
    for app in ("search", "web", "browser-attached"):
        assert (apt.root / "usr/lib/cos/apps" / app / "app.json").read_bytes() == (
            browser_source / "apps" / app / "app.json"
        ).read_bytes()


@pytest.mark.parametrize(("field", "value"), [
    ("source", "../other-product"),
    ("destination", "/usr/lib/cos/claw-browser-host"),
    ("destination", "etc/chromium/policies/managed/claw-browser.json"),
    ("apps", ["other-app"]),
])
def test_installed_asset_declarations_refuse_escapes_and_undeclared_owners(tmp_path, field, value):
    source, package = release.stage.load_package("browser")
    package = copy.deepcopy(package)
    package["installed_assets"][0][field] = value
    with pytest.raises(ValueError):
        stage_assets(source, package, tmp_path / "payload", ["browser-attached"], ignore=release.stage.IGNORE)
    assert not (tmp_path / "payload").exists()


def test_installed_assets_preflight_every_target_before_copying(tmp_path):
    source, package = release.stage.load_package("browser")
    root = tmp_path / "payload"
    (root / LAUNCHER).parent.mkdir(parents=True)
    (root / LAUNCHER).write_bytes(b"an existing owner's file")
    with pytest.raises(ValueError, match="Conflicting"):
        stage_assets(source, package, root, ["browser-attached"], ignore=release.stage.IGNORE)
    assert (root / LAUNCHER).read_bytes() == b"an existing owner's file"
    assert not (root / EXTENSION).exists()


def test_installed_assets_refuse_links_to_other_product_payloads(tmp_path, browser_source):
    outside = tmp_path / "other-product.txt"
    outside.write_text("not Browser")
    (browser_source / "extension/escape").symlink_to(outside)
    package = json.loads((browser_source / "package.json").read_text())
    with pytest.raises(ValueError, match="symlink"):
        stage_assets(browser_source, package, tmp_path / "payload", ["browser-attached"], ignore=release.stage.IGNORE)
    assert not (tmp_path / "payload").exists()
