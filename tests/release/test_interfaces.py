import json
import sys

import pytest

import release
import release_interfaces
import release_development
from release_common import ROOT, run, write_json
from release_publish import release_assets, verify_artifacts


def test_active_release_modules_do_not_import_the_retired_exporter():
    result = run([sys.executable, "-c", (
        "import sys; sys.path.insert(0, 'tools'); "
        "sys.modules['release_interfaces'] = None; "
        "import release, release_publish; print('legacy exporter not imported')"
    )])
    assert result.stdout.strip() == b"legacy exporter not imported"


def test_an_independent_app_release_does_not_require_source_fixtures_or_unrelated_interfaces(tmp_path, monkeypatch):
    plan = release.make_plan("capability:http", "1.0.0")
    assert plan["include_fixtures"] is False
    monkeypatch.setattr(release, "build_archive", lambda *args: pytest.fail("source fixtures were not requested"))
    monkeypatch.setattr(release_interfaces, "build_interfaces", lambda *args: pytest.fail("retired exporter called"))
    release.build(plan, "all", tmp_path / "packages")
    packages, development, interfaces = verify_artifacts(plan, tmp_path / "packages")
    assert len(packages) == 1 and not development and not interfaces
    assert not list((tmp_path / "packages").glob("*.tar.*"))


def test_notifications_do_not_implicitly_export_product_ui_or_config_libraries(tmp_path, monkeypatch, signing):
    plan = release.make_plan("notifications", "1.2.3")
    metadata = json.loads((ROOT / "products/notifications/package.json").read_bytes())
    assert "native_libraries" not in metadata
    assert release_development.RETIRED_NATIVE_INTERFACES.issubset(metadata["native_packages"])
    monkeypatch.setattr(release_interfaces, "build_interfaces", lambda *args: pytest.fail("retired exporter called"))
    release.build(plan, "all", tmp_path / "packages")
    report = json.loads((tmp_path / "packages/build-record-all.json").read_text())
    assert report["interfaces"] == {}
    assert not list((tmp_path / "packages").glob("*.tar.gz"))
    development, interfaces = report["development"], report["interfaces"]
    assert len(report["packages"]) == 1 and development == {} and interfaces == {}
    assets = release_assets(
        plan, "notifications", list((tmp_path / "packages").glob("*.deb")), tmp_path / "assets", signing,
        development=development, interfaces=interfaces, artifact_directory=tmp_path / "packages",
    )
    metadata = json.loads((assets / "release.json").read_text())
    assert metadata["interfaces"] is None and metadata["development"] is None
    assert not list(assets.glob("*.tar.*"))
    signing.verify(assets / "SHA256SUMS.asc", assets / "SHA256SUMS")


@pytest.mark.parametrize("name", sorted(release_development.RETIRED_NATIVE_INTERFACES))
@pytest.mark.parametrize("fixtures", [False, True])
def test_reintroduced_config_util_exports_fail_before_package_writes(tmp_path, monkeypatch, name, fixtures):
    plan = release.make_plan("notifications", "1.2.3", fixtures=fixtures)
    load = release.stage.load_package

    def reintroduced(product, kind="product"):
        source, metadata = load(product, kind)
        if product == "notifications" and kind == "product":
            metadata = {**metadata, "native_libraries": {name: {"path": name}}}
        return source, metadata

    monkeypatch.setattr(release.stage, "load_package", reintroduced)
    with pytest.raises(ValueError, match="config/util release exports are retired"):
        release.build(plan, "all", tmp_path / "packages")
    assert not (tmp_path / "packages").exists()
    with pytest.raises(ValueError, match="config/util release exports are retired"):
        release_development.build_archive(plan, "notifications", tmp_path / "fixtures")
    assert not list((tmp_path / "fixtures").iterdir())


@pytest.mark.parametrize("kind", ["record", "archive"])
def test_retired_interface_inputs_are_rejected_by_complete_release_verification(tmp_path, kind):
    plan = release.make_plan("capability:http", "1.0.0")
    output = tmp_path / "packages"
    release.build(plan, "all", output)
    if kind == "record":
        record = json.loads((output / "build-record-all.json").read_bytes())
        record["interfaces"] = {"notifications": {"filename": "claw-app-interfaces-1.0.0.tar.gz"}}
        write_json(output / "build-record-all.json", record)
    else:
        (output / "claw-app-interfaces-1.0.0.tar.gz").write_bytes(b"historical fixture, not a release input")
    with pytest.raises(ValueError, match="Retired App.*interface archives"):
        verify_artifacts(plan, output)


def test_legacy_interfaces_cannot_be_signed_even_when_explicitly_supplied(tmp_path, monkeypatch, signing):
    plan = release.make_plan("notifications", "1.2.3")
    monkeypatch.setattr(signing, "sign", lambda *args, **kwargs: pytest.fail("retired artifacts must not be signed"))
    with pytest.raises(ValueError, match="cannot be signed or published"):
        release_assets(
            plan, "notifications", [], tmp_path / "assets", signing, development={},
            artifact_directory=tmp_path,
            interfaces={"notifications": {"filename": "claw-app-interfaces-1.2.3.tar.gz"}},
        )
    assert not (tmp_path / "assets").exists()


def test_retired_exporter_cli_fails_before_creating_output(tmp_path):
    output = tmp_path / "legacy-export"
    result = run([sys.executable, "tools/release_interfaces.py", "--version", "1.2.3", "--output", output],
                 check=False)
    assert result.returncode == 2
    assert b"config/util release exports are retired" in result.stderr
    assert not output.exists()
