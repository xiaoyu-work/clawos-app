import hashlib
import io
import json
import sys
import tarfile

import pytest

import release
from release_common import ROOT, digest, run
from release_development import build_archive, verify_archive, validate_interface
from release_publish import verify_artifacts


def extract(archive, destination):
    with tarfile.open(archive) as stream:
        stream.extractall(destination, filter="data")


def test_content_addressed_fixture_is_deterministic_and_stages_the_complete_declared_closure(tmp_path):
    plan = release.make_plan("capability:document-engine", "1.0.0")
    first = build_archive(plan, "capability:document-engine", tmp_path / "first")
    second = build_archive(plan, "capability:document-engine", tmp_path / "second")
    assert first == second
    assert first["filename"] == f"claw-app-development-{first['sha256']}.tar.xz"
    archive = tmp_path / "first" / first["filename"]
    manifest = verify_archive(archive, first, plan)
    assert manifest["apps"] == ["doc"]
    assert {(group["kind"], group["name"], group["role"]) for group in manifest["groups"]} == {
        ("capability", "document-engine", "selected"),
        ("product", "files", "python-dependency"),
    }
    root = tmp_path / "extracted"
    extract(archive, root)
    projection = json.loads((root / "products/files/package.json").read_text())
    assert "native" not in projection and "native_assets" not in projection
    assert not (root / "products/files/native").exists()
    assert not (root / "platform.lock.json").exists()
    assert not (root / "tools/platform_dependency.py").exists()
    staged = tmp_path / "staged"
    result = run([sys.executable, root / "tools/stage.py", "document-engine", "--kind", "capability",
                  "--root", staged], cwd=root, env={"PYTHONDONTWRITEBYTECODE": "1"})
    assert json.loads(result.stdout) == ["doc"]
    run([sys.executable, root / "tools/stage.py", "--shared", "--root", staged], cwd=root)
    for relative in ("usr/lib/cos/apps/doc/server.py", "usr/lib/cos/python/claw_files/document.py",
                     "usr/lib/cos/python/_shared/atomic.py", "usr/lib/cos/python/canonical_argv.py"):
        assert (staged / relative).read_bytes() == (root / "payload" / relative).read_bytes()
    assert (root / "payload/usr/lib/cos/python/pptx/__init__.py").is_file()
    assert (root / "payload/usr/lib/cos/python/python_pptx-1.0.2.dist-info/LICENSE").is_file()
    assert not (root / "payload/usr/lib/cos/apps/fs").exists()
    assert not (root / "payload/usr/bin").exists()


def test_notifications_do_not_export_undeclared_product_libraries(tmp_path):
    plan = release.make_plan("notifications", "1.0.0")
    record = build_archive(plan, "notifications", tmp_path / "archives")
    archive = tmp_path / "archives" / record["filename"]
    manifest = verify_archive(archive, record, plan)
    assert manifest["native_interfaces"] == {}
    assert set(manifest["apps"]) == {"notify", "cosmic-notifications"}
    root = tmp_path / "extracted"
    extract(archive, root)
    assert not (root / "interfaces").exists()
    assert not (root / "products/notifications/native").exists()
    assert not (root / "tools/native_build.py").exists()
    assert not (root / "payload/usr/bin/cosmic-notifications").exists()


@pytest.mark.parametrize("injection", ["declaration", "payload"])
def test_fixtures_cannot_restore_retired_config_util_exports_with_rehashed_metadata(tmp_path, injection):
    plan = release.make_plan("capability:http", "1.0.0")
    record = build_archive(plan, "capability:http", tmp_path / "original")
    source = tmp_path / "original" / record["filename"]
    candidate = tmp_path / "changed.tar.xz"
    extra = b"retired product interface\n"
    path = "interfaces/cosmic-notifications-config/Cargo.toml"
    with tarfile.open(source) as original, tarfile.open(candidate, "w:xz") as output:
        members = original.getmembers()
        manifest = json.load(original.extractfile("manifest.json"))
        if injection == "declaration":
            manifest["native_interfaces"] = {
                "cosmic-notifications-config": {"path": "interfaces/cosmic-notifications-config"},
            }
        else:
            manifest["files"].update({
                "interfaces": {"type": "directory", "mode": 0o755},
                "interfaces/cosmic-notifications-config": {"type": "directory", "mode": 0o755},
                path: {"type": "file", "mode": 0o644, "size": len(extra),
                       "sha256": hashlib.sha256(extra).hexdigest()},
            })
        for member in members:
            if member.name == "manifest.json":
                body = json.dumps(manifest, sort_keys=True).encode()
                member.size = len(body)
                output.addfile(member, io.BytesIO(body))
            else:
                output.addfile(member, original.extractfile(member) if member.isfile() else None)
        if injection == "payload":
            for name in ("interfaces", "interfaces/cosmic-notifications-config", path):
                member = tarfile.TarInfo(name)
                member.mtime = plan["source_date_epoch"]
                if name == path:
                    member.mode = 0o644
                    member.size = len(extra)
                    output.addfile(member, io.BytesIO(extra))
                else:
                    member.type = tarfile.DIRTYPE
                    member.mode = 0o755
                    output.addfile(member)
    checksum = digest(candidate)
    artifact = candidate.with_name(f"claw-app-development-{checksum}.tar.xz")
    candidate.rename(artifact)
    changed = {**record, "filename": artifact.name, "sha256": checksum, "size": artifact.stat().st_size}
    with pytest.raises(ValueError, match="Retired|retired"):
        verify_archive(artifact, changed, plan)


def test_interface_validation_refuses_build_hooks_and_undeclared_product_dependencies(tmp_path):
    root = tmp_path / "interface"
    (root / "src").mkdir(parents=True)
    (root / "src/lib.rs").write_text("pub struct Fixture;\n")
    manifest = root / "Cargo.toml"
    manifest.write_text('[package]\nname="fixture"\nversion="1.0.0"\n')
    roots = {"fixture": (root, "fixture-owner")}
    assert validate_interface("fixture", root, roots)["path"] == "interfaces/fixture"
    (root / "build.rs").write_text("fn main() {}\n")
    with pytest.raises(ValueError, match="build hooks"):
        validate_interface("fixture", root, roots)
    (root / "build.rs").unlink()
    with manifest.open("a") as output:
        output.write('[dependencies]\nproduct={path="../product-implementation"}\n')
    with pytest.raises(ValueError, match="undeclared product"):
        validate_interface("fixture", root, roots)


def test_fixture_tampering_and_missing_release_archives_are_refused(tmp_path):
    plan = release.make_plan("capability:http", "1.0.0", fixtures=True)
    directory = tmp_path / "release"
    release.build(plan, "all", directory)
    packages, development, interfaces = verify_artifacts(plan, directory)
    assert interfaces == {}
    assert [path.name for path in packages] == ["claw-cap-http_1.0.0_all.deb"]
    record = development["capability:http"]
    archive = directory / record["filename"]
    original = archive.read_bytes()
    archive.write_bytes(original + b"mutated")
    with pytest.raises(ValueError, match="digest"):
        verify_artifacts(plan, directory)
    archive.unlink()
    with pytest.raises(ValueError, match="digest"):
        verify_artifacts(plan, directory)
    assert not any("development" in entry["control"].get("Depends", "") for entry in (
        json.loads((directory / "build-record-all.json").read_text())["packages"]
    ))


def test_mail_fixture_preserves_the_working_extension_without_the_mozilla_fork(tmp_path):
    plan = release.make_plan("mail", "1.0.0")
    record = build_archive(plan, "mail", tmp_path / "archives")
    root = tmp_path / "extracted"
    extract(tmp_path / "archives" / record["filename"], root)
    assert (root / "products/mail/build-extension.py").is_file()
    assert (root / "products/mail/extension/manifest.json").is_file()
    assert (root / "payload/usr/lib/thunderbird/distribution/extensions/claw-mail-ai@claw.os.xpi").is_file()
    assert not (root / "products/mail/native").exists()
