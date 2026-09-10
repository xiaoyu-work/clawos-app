import hashlib
from pathlib import Path
import zipfile

import pytest

from release_common import config
import release_wheels


def test_real_pinned_powerpoint_dependency_has_one_owner_and_retains_its_license(tmp_path):
    release_wheels.stage_wheels("files", tmp_path, owner="claw-app-files")
    assert (tmp_path / "usr/lib/cos/python/pptx/__init__.py").is_file()
    metadata = tmp_path / "usr/lib/cos/python/python_pptx-1.0.2.dist-info"
    assert "MIT License" in (metadata / "LICENSE").read_text()
    assert (tmp_path / "usr/share/doc/claw-app-files/licenses/python-pptx/LICENSE").read_bytes() == (
        metadata / "LICENSE"
    ).read_bytes()
    assert "Requires-Dist: lxml" in (metadata / "METADATA").read_text()


def test_cached_wheel_mutation_is_rejected_without_downloading_a_fallback(tmp_path, monkeypatch):
    specification = config()["python_wheels"]["files"][0]
    monkeypatch.setattr(release_wheels, "ROOT", tmp_path)
    filename = Path(specification["url"]).name
    cached = tmp_path / "build/release-wheels" / specification["sha256"] / filename
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"changed cached dependency")
    monkeypatch.setattr(release_wheels.urllib.request, "urlopen", lambda *args, **kwargs: pytest.fail("no fallback download"))
    with pytest.raises(ValueError, match="Cached.*digest"):
        release_wheels.wheel_path(specification)


def test_wheel_cannot_inject_an_arbitrary_path_even_when_fixture_digest_matches(tmp_path, monkeypatch):
    specification = {**config()["python_wheels"]["files"][0]}
    wheel = tmp_path / "unsafe.whl"
    metadata = "python_pptx-1.0.2.dist-info"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"{metadata}/WHEEL", "Root-Is-Purelib: true\nTag: py3-none-any\n")
        archive.writestr(f"{metadata}/LICENSE", "MIT License fixture")
        archive.writestr("../escape", "not allowed")
    specification["size"] = wheel.stat().st_size
    specification["sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
    monkeypatch.setattr(release_wheels, "config", lambda: {"python_wheels": {"files": [specification]}})
    monkeypatch.setattr(release_wheels, "wheel_path", lambda _: wheel)
    with pytest.raises(ValueError, match="escapes"):
        release_wheels.stage_wheels("files", tmp_path / "installed", owner="claw-app-files")
    assert not (tmp_path / "escape").exists()
