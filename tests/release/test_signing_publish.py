import json
import subprocess

import pytest

import release_publish
import release_signing
from release_development import build_archive
from release_common import ROOT, command_environment, config, digest, run
from release_publish import GitHub, existing_release, previous_snapshot, release_tag
from release_signing import Signing


def test_pinned_public_key_matches_the_parent_installer_contract(tmp_path):
    with Signing(tmp_path / "public-only") as signing:
        assert signing.fingerprint == "ADBA1957E712B6C80B4CC8736C044D6F411416AF"
        with pytest.raises(ValueError, match="Unsigned"):
            signing.sign(tmp_path / "not-created", tmp_path / "not-signed")


def test_signing_key_cannot_be_replaced_by_a_runtime_override(tmp_path, signing):
    settings = {**signing.settings, "signing_fingerprint": "0" * 40}
    with pytest.raises(ValueError, match="fingerprint"):
        with Signing(tmp_path / "wrong-fingerprint", settings):
            pass
    assert not (tmp_path / "wrong-fingerprint").exists()


def test_passphrase_is_only_stdin_never_an_argument_or_inherited_secret(tmp_path, signing, monkeypatch):
    original = release_signing.run
    calls = []

    def recording(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return original(arguments, **kwargs)

    monkeypatch.setattr(release_signing, "run", recording)
    content = tmp_path / "SHA256SUMS"
    content.write_text("fixture checksum content\n")
    signing.sign(content, tmp_path / "SHA256SUMS.asc", armored=True)
    signatures = [(arguments, kwargs) for arguments, kwargs in calls if "--detach-sign" in arguments]
    assert len(signatures) == 1
    arguments, kwargs = signatures[0]
    assert arguments[arguments.index("--passphrase-fd") + 1] == "0"
    assert kwargs["input"] == b"release fixture passphrase\n"
    assert "release fixture passphrase" not in repr(arguments)
    assert "--passphrase" not in arguments


def test_child_commands_never_inherit_private_signing_material(monkeypatch):
    monkeypatch.setenv("CLAW_APPS_APT_SIGNING_PRIVATE_KEY", "fixture key material")
    monkeypatch.setenv("CLAW_APPS_APT_SIGNING_PASSPHRASE", "fixture passphrase")
    environment = command_environment({"CLAW_APPS_APT_SIGNING_PASSPHRASE": "also forbidden"})
    assert "CLAW_APPS_APT_SIGNING_PRIVATE_KEY" not in environment
    assert "CLAW_APPS_APT_SIGNING_PASSPHRASE" not in environment


def test_github_transport_failure_is_not_treated_as_an_absent_repository(monkeypatch):
    monkeypatch.setattr(release_publish, "run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args, 1, b"", b"network unavailable",
    ))
    with pytest.raises(ValueError, match="transport"):
        GitHub().api("git/ref/heads/app-apt", allowed=(200, 404))
    monkeypatch.setattr(release_publish, "run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args, 1, b"HTTP/2.0 403 Forbidden\r\n\r\n{}", b"forbidden",
    ))
    with pytest.raises(ValueError, match="403"):
        GitHub().api("git/ref/heads/app-apt", allowed=(200, 404))


def test_github_success_is_parsed_without_weakening_http_error_checks(monkeypatch):
    monkeypatch.setattr(release_publish, "run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args, 0, b'HTTP/2.0 200 OK\r\nContent-Type: application/json\r\n\r\n{"enabled":true}', b"",
    ))
    assert GitHub().api("immutable-releases") == (200, {"enabled": True})


def test_prior_immutable_versions_protect_against_regression_after_an_incomplete_apt_push():
    class History:
        def api(self, endpoint, **kwargs):
            return 200, [
                {"tag_name": "app-files-v2.0.0-rc1", "draft": False, "immutable": True},
                {"tag_name": "app-mail-v9.0.0", "draft": False, "immutable": True},
            ]

    with pytest.raises(ValueError, match="newer immutable"):
        release_publish.check_published_versions(History(), ["files"], "1.9.0")
    release_publish.check_published_versions(History(), ["files"], "2.0.0")
    release_publish.check_published_versions(History(), ["capability:http"], "1.0.0")


def test_verified_empty_initial_state_is_distinct_from_lost_history(tmp_path):
    class Empty:
        settings = config()

        def api(self, endpoint, **kwargs):
            if endpoint.startswith("git/ref/"):
                return 404, {"message": "Not Found"}
            return 200, []

    assert previous_snapshot(Empty(), tmp_path / "none", initialize=True) == (None, None)
    with pytest.raises(ValueError, match="first publication"):
        previous_snapshot(Empty(), tmp_path / "none", initialize=False)

    class Lost(Empty):
        def api(self, endpoint, **kwargs):
            if endpoint.startswith("releases"):
                return 200, [{"tag_name": "app-files-v1.0.0"}]
            return super().api(endpoint, **kwargs)

    with pytest.raises(ValueError, match="restore"):
        previous_snapshot(Lost(), tmp_path / "none", initialize=True)


def test_immutable_release_tags_cannot_be_rebound_or_mutable(tmp_path):
    class Existing:
        def __init__(self, sha="a" * 40, immutable=True):
            self.sha = sha
            self.immutable = immutable

        def api(self, endpoint, **kwargs):
            if endpoint.startswith("releases/"):
                return 200, {"draft": False, "immutable": self.immutable}
            return 200, {"object": {"type": "commit", "sha": self.sha}}

    assert existing_release(Existing(), "app-files-v1.0.0", "a" * 40)["immutable"]
    with pytest.raises(ValueError, match="rebind"):
        existing_release(Existing("b" * 40), "app-files-v1.0.0", "a" * 40)
    with pytest.raises(ValueError, match="immutable"):
        existing_release(Existing(immutable=False), "app-files-v1.0.0", "a" * 40)
    assert release_tag("files", "1.2.3") == "app-files-v1.2.3"
    assert release_tag("capability:http", "1.2.3") == "cap-http-v1.2.3"
    assert release_tag("support", "1.2.3") == "support-v1.2.3"
    tag = release_tag("files", "1.2.3~rc1-2")
    assert tag == "app-files-v1.2.3-rc1-2"
    run(["git", "check-ref-format", f"refs/tags/{tag}"])


def test_independent_release_assets_sign_debs_and_explicit_development_archive(tmp_path, deb, signing):
    package = deb("claw-app-fixture")
    plan = {
        "version": "1.0.0", "source_revision": "a" * 40,
        "source_date_epoch": 1700000000, "selections": ["support"],
        "packages": [{"selection": "support", "package": "claw-app-fixture"}],
    }
    record = build_archive(plan, "support", tmp_path / "input")
    assets = release_publish.release_assets(plan, "support", [package], tmp_path / "assets", signing,
                                           development={"support": record}, artifact_directory=tmp_path / "input")
    assert {path.name for path in assets.iterdir()} == {
        package.name, record["filename"], "release.json", "SHA256SUMS", "SHA256SUMS.asc",
    }
    signing.verify(assets / "SHA256SUMS.asc", assets / "SHA256SUMS")
    assert f"{digest(package)}  {package.name}\n" in (assets / "SHA256SUMS").read_text()
    manifest = json.loads((assets / "release.json").read_text())
    assert manifest["packages"][0]["sha256"] == digest(package)
    assert manifest["development"] == record


def test_publication_scripts_have_no_unsafe_republish_or_unsigned_fallback():
    publisher = (ROOT / "tools/release_publish.py").read_text()
    assert "--clobber" not in publisher
    assert "--force" not in publisher
    assert "--allow-unauthenticated" not in publisher
    refresh = (ROOT / ".github/workflows/release-refresh.yml").read_text()
    assert "app-apt-publication" in refresh and "schedule:" in refresh
    assert "release_publish.py refresh" in refresh
    assert "native_build.py" not in refresh
