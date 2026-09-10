import io
import struct
import sys
import tarfile

import pytest

import release
from release_common import ROOT, digest, fields, run, version
from release_publish import verify_artifacts


def contents(package):
    with tarfile.open(fileobj=io.BytesIO(run(["dpkg-deb", "--fsys-tarfile", package]).stdout)) as archive:
        return {member.name.removeprefix("./"): member for member in archive.getmembers()}


@pytest.mark.parametrize("value", ["1.2.3", "0.1.0-1", "2.0.0~rc2-3"])
def test_debian_release_version_accepts_an_explicit_bounded_grammar(value):
    assert version(value) == value


@pytest.mark.parametrize("value", ["", "v1.0.0", "1:1.0.0", "01.0.0", "1.2", "1.2.3\n",
                                       "1.2.3;echo bad", "../1.2.3", "1.0.0-0", "1.0.0~rc0"])
def test_release_versions_cannot_inject_tags_paths_or_shell(value):
    with pytest.raises(ValueError):
        version(value)


def test_all_identities_have_exactly_one_headless_or_desktop_package_owner():
    plan = release.make_plan("all", "1.0.0")
    assert len([item for item in plan["selections"] if item not in ("support", "sets")]) == 28
    agent, desktop = {}, {}
    for entry in plan["packages"]:
        if entry["architecture"] == "arm64":
            continue
        for app_id in entry["apps"]:
            destination = agent if entry["variant"] == "agent" else desktop
            assert app_id not in destination
            destination[app_id] = entry["package"]
    assert len(agent) == 63
    assert len(desktop) == 12
    assert not set(agent).intersection(desktop)
    assert desktop["cosmic-files"] == "claw-app-files-desktop"
    assert agent["db"] == agent["kv"] == "claw-cap-storage-sdk"
    headless = release.dependencies(release.packages_for("sets")[0], "1.0.0")
    assert "claw-cap-storage-sdk" in headless and "claw-app-files" in headless
    assert not any(name.endswith("-desktop") for name in headless)


def test_selected_python_products_do_not_schedule_unrelated_native_builds():
    plan = release.make_plan("capability:http", "1.2.3")
    assert [job["architecture"] for job in plan["matrix"]["include"]] == ["all"]
    assert [entry["package"] for entry in plan["packages"]] == ["claw-cap-http"]
    plan = release.make_plan("files", "1.2.3")
    assert [job["architecture"] for job in plan["matrix"]["include"]] == ["all", "amd64", "arm64"]
    assert {entry["package"] for entry in plan["packages"]} == {"claw-app-files", "claw-app-files-desktop"}


@pytest.mark.parametrize("product", ["calendar", "clipboard", "desktop-widgets"])
def test_standalone_applet_packages_require_the_versioned_os_service_only_for_desktop(product, tmp_path):
    packages = release.packages_for(product)
    native = [entry for entry in packages if entry["variant"] == "desktop"]
    assert {entry["architecture"] for entry in native} == {"amd64", "arm64"}
    for entry in packages:
        dependencies = release.dependencies(entry, "1.0.0")
        assert ("claw-os-applet-services-v1 (= 1)" in dependencies) == (entry["variant"] == "desktop")
        assert "claw-os-app-runtime-v1" in dependencies
        root = tmp_path / entry["package"] / entry["architecture"]
        root.mkdir(parents=True)
        release.write_control(root, entry, release.make_plan(product, "1.0.0"))
        control = fields((root / "DEBIAN/control").read_text().strip())
        former = "claw-os-desktop" if entry["variant"] == "desktop" else "claw-os-agent"
        assert control["Breaks"] == control["Replaces"] == f"{former} (<< 1:0.3.0)"


def test_support_package_declares_the_idna_compatibility_bounds(tmp_path):
    release.build(release.make_plan("support", "1.2.3"), "all", tmp_path / "packages")
    package = tmp_path / "packages/claw-app-support_1.2.3_all.deb"
    control = fields(run(["dpkg-deb", "-f", package]).stdout.decode().strip())
    dependencies = {value.strip() for value in control["Depends"].split(",")}
    assert {"python3-idna (>= 3.3)", "python3-idna (<< 4)", "claw-os-app-runtime-v1"} <= dependencies
    assert control["Provides"] == "claw-app-support-v1"
    assert control["Breaks"] == control["Replaces"] == "claw-os-agent (<< 1:0.3.0)"
    payload = tmp_path / "payload"
    run(["dpkg-deb", "--extract", package, payload])
    for relative in ("_shared/__init__.py", "gateway/__init__.py", "canonical_argv.py"):
        assert (payload / "usr/lib/cos/python" / relative).read_bytes() == (
            ROOT / "shared/python" / relative
        ).read_bytes()


def test_real_packages_are_deterministic_and_have_nonconflicting_ownership(tmp_path):
    plan = release.make_plan("files,capability:document-engine,mail,support", "1.2.3")
    outputs = [tmp_path / "first", tmp_path / "second"]
    for output in outputs:
        release.build(plan, "all", output)
    first, second = outputs
    packages = sorted(first.glob("*.deb"))
    assert packages
    owned = {}
    for package in packages:
        assert digest(package) == digest(second / package.name)
        entries = contents(package)
        assert not any(path.startswith(("var/", "home/")) for path in entries)
        for path, entry in entries.items():
            assert entry.uid == entry.gid == 0
            if entry.isfile() or entry.issym():
                assert path not in owned, (package.name, owned.get(path), path)
                owned[path] = package.name
    assert owned["usr/lib/cos/python/claw_files/document.py"].startswith("claw-app-files_")
    assert owned["usr/lib/cos/python/pptx/__init__.py"].startswith("claw-app-files_")
    assert owned["usr/lib/cos/python/python_pptx-1.0.2.dist-info/LICENSE"].startswith("claw-app-files_")
    assert owned["usr/lib/cos/python/_shared/atomic.py"].startswith("claw-app-support_")
    assert owned["usr/lib/cos/python/canonical_argv.py"].startswith("claw-app-support_")
    xpi = "usr/lib/thunderbird/distribution/extensions/claw-mail-ai@claw.os.xpi"
    assert owned[xpi].startswith("claw-app-mail-desktop_")
    mail = fields(run(["dpkg-deb", "-f", first / "claw-app-mail_1.2.3_all.deb"]).stdout.decode().strip())
    assert "thunderbird" not in mail["Depends"]
    desktop = fields(run(["dpkg-deb", "-f", first / "claw-app-mail-desktop_1.2.3_all.deb"]).stdout.decode().strip())
    assert "thunderbird" in desktop["Depends"]
    assert "claw-app-mail (= 1.2.3)" in desktop["Depends"]
    assert desktop["Replaces"] == "claw-os-agent (<< 1:0.3.0)"
    doc = fields(run(["dpkg-deb", "-f", first / "claw-cap-document-engine_1.2.3_all.deb"]).stdout.decode().strip())
    assert "claw-app-files" in doc["Depends"] and "claw-app-python-claw-files-v1" in doc["Depends"]
    assert "claw_os_sdk" not in repr(owned)
    assert not any("test_" in path or "Cargo.toml" in path for path in owned)
    assert doc["Breaks"] == doc["Replaces"] == "claw-os-agent (<< 1:0.3.0)"
    assert "claw-os-app-runtime-v1" in doc["Depends"]
    assert "python3-pptx" not in doc["Depends"]
    assert doc["X-Claw-App-Ids"] == "doc"


def test_build_refuses_to_overwrite_a_version_and_publish_requires_every_architecture(tmp_path):
    plan = release.make_plan("files", "1.2.3")
    release.build(plan, "all", tmp_path / "packages")
    with pytest.raises(ValueError, match="every|exactly"):
        verify_artifacts(plan, tmp_path / "packages")
    with pytest.raises(ValueError, match="overwrite"):
        release.build(plan, "all", tmp_path / "packages")


def test_native_packages_refuse_a_placeholder_or_wrong_architecture(tmp_path, monkeypatch):
    entry = release.packages_for("capture")[0]
    entry["architecture"] = run(["dpkg", "--print-architecture"]).stdout.decode().strip()
    root = tmp_path / "installed"
    binary = root / "usr/lib/cos/apps/cosmic-screenshot/bin/cosmic-screenshot"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"not an executable")
    binary.chmod(0o755)
    monkeypatch.setattr(release, "require_platform_artifact", lambda: None)
    monkeypatch.setattr(release.subprocess, "run", lambda *args, **kwargs: None)
    # Keep the Debian host architecture query real without invoking a product build.
    monkeypatch.setattr(release, "run", lambda args, **kwargs: type(
        "Result", (), {"stdout": entry["architecture"].encode()}
    )())
    with pytest.raises(ValueError, match="runnable"):
        release.native_payload(root, entry)
    binary.write_bytes(
        b"\x7fELF\x02\x01" + b"\x00" * 10
        + struct.pack("<HH", 2, 183 if entry["architecture"] == "amd64" else 62)
    )
    with pytest.raises(ValueError, match="runnable"):
        release.native_payload(root, entry)


def test_native_libraries_are_never_published_as_runnable_apps(tmp_path, monkeypatch):
    original = release.stage.load_package

    def library(name, kind):
        source, package = original(name, kind)
        return source, {key: value for key, value in package.items() if key != "native_kind"}

    monkeypatch.setattr(release.stage, "load_package", library)
    with pytest.raises(ValueError, match="native library"):
        release.native_payload(tmp_path, release.packages_for("capture")[0])


def test_support_release_runs_shared_contracts_and_native_release_does_not_build_examples(monkeypatch):
    calls = []
    monkeypatch.setattr(release, "require_platform_artifact", lambda: None)
    monkeypatch.setattr(release.subprocess, "run", lambda command, **kwargs: calls.append(command))
    plan = {"selections": ["support"], "packages": []}
    release.test_selected(plan, "all")
    assert calls[0][-2:] == ["tools/test.py", "--shared"]
    source = (ROOT / "tools/native_build.py").read_text()
    assert 'options.command == "build" and not options.release' in source
    assert '"--release"' in source and '"--install-root"' in source


def test_release_commands_refuse_the_legacy_os_source_transport():
    with pytest.raises(ValueError, match="legacy OS Git/source"):
        release.require_platform_artifact({"repository": "https://github.com/example/os.git", "revision": "a" * 40})
    pin = {"version": "1.0.0", "url": "https://example.invalid/platform-1.0.0.tar.gz",
           "sha256": "a" * 64, "runtime_abi": 1}
    release.require_platform_artifact(pin)
    for invalid in (
        {"artifact": {"sha256": "a" * 64}},
        {**pin, "repository": "https://github.com/example/os.git", "revision": "a" * 40},
        {**pin, "url": "http://example.invalid/platform-1.0.0.tar.gz"},
        {**pin, "runtime_abi": 2},
    ):
        with pytest.raises(ValueError):
            release.require_platform_artifact(invalid)


def test_native_installer_rejects_non_release_or_host_roots_before_fetching_inputs(tmp_path):
    command = [sys.executable, ROOT / "tools/native_build.py", "capture", "build", "--install-root"]
    missing_release = run([*command, tmp_path / "installed"], check=False)
    assert missing_release.returncode != 0
    assert b"requires build --release" in missing_release.stderr
    host_root = run([*command, "/", "--release"], check=False)
    assert host_root.returncode != 0
    assert b"explicit directory under build/" in host_root.stderr
