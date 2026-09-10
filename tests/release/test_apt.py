from datetime import timedelta
import os
import pwd
import shutil
import subprocess

import pytest

from release_apt import compose, now_utc, verify_repository
from release_common import digest, fields, run
import release


class IsolatedApt:
    def __init__(self, root, repository, signing):
        self.root = root
        for path in ("etc/apt", "var/lib/apt/lists/partial", "var/lib/dpkg/updates",
                     "var/cache/apt/archives/partial", "var/log/apt"):
            (root / path).mkdir(parents=True)
        (root / "var/lib/dpkg/status").write_text("")
        self.configuration = root / "apt.conf"
        self.configuration.write_text(f'''
Dir "{root}";
Dir::State "{root}/var/lib/apt";
Dir::State::status "{root}/var/lib/dpkg/status";
Dir::State::lists "{root}/var/lib/apt/lists";
Dir::Cache "{root}/var/cache/apt";
Dir::Log "{root}/var/log/apt";
Dir::Etc "{root}/etc/apt";
Dir::Etc::sourcelist "sources.list";
Dir::Etc::sourceparts "-";
Dir::Etc::main "-";
Dir::Etc::parts "-";
Dir::Etc::trusted "{root}/etc/apt/trusted.gpg";
Dir::Etc::trustedparts "-";
APT::Architecture "amd64";
APT::Architectures {{ "amd64"; }};
APT::Sandbox::User "{pwd.getpwuid(os.geteuid()).pw_name}";
APT::Get::AllowUnauthenticated "false";
APT::Install-Recommends "false";
Acquire::Languages "none";
Acquire::Check-Valid-Until "true";
Acquire::AllowInsecureRepositories "false";
Acquire::AllowDowngradeToInsecureRepositories "false";
DPkg::Options {{
  "--root={root}";
  "--admindir={root}/var/lib/dpkg";
  "--log={root}/var/log/dpkg.log";
  "--force-not-root";
}};
''')
        key = root / "etc/apt/trusted.gpg"
        shutil.copy2(signing.keyring, key)
        self.source_file = root / "etc/apt/sources.list"
        self.source_file.write_text(
            f"deb [arch=amd64 signed-by={key} by-hash=force] {repository.as_uri()} trixie main\n"
        )

    def call(self, *arguments, check=True):
        return run(["apt-get", *arguments], env={
            "APT_CONFIG": str(self.configuration), "PATH": os.environ["PATH"] + ":/usr/sbin:/sbin",
        }, check=check)

    def update(self, *, check=True):
        return self.call("update", "--error-on=any", "-qq", check=check)

    def installed(self, name):
        return run(["dpkg-query", f"--admindir={self.root}/var/lib/dpkg", "-W", "-f=${Version}", name]).stdout.decode()


def test_signed_selected_product_publish_retains_other_packages_and_prior_by_hash(tmp_path, deb, signing):
    first = compose([deb("claw-app-alpha"), deb("claw-app-beta")],
                    tmp_path / "first", signing, initialize=True)
    previous = verify_repository(first, signing)
    second = compose([deb("claw-app-alpha", "2.0.0", b"new alpha")],
                     tmp_path / "second", signing, previous=first)
    current = verify_repository(second, signing)
    assert {(record["package"], record["version"]) for record in current["packages"]} == {
        ("claw-app-alpha", "1.0.0"), ("claw-app-alpha", "2.0.0"), ("claw-app-beta", "1.0.0"),
    }
    for path, value in previous["indexes"].items():
        assert current["indexes"][path] == value
        assert (first / "dists/trixie" / path).read_bytes() == (second / "dists/trixie" / path).read_bytes()


def test_real_apt_install_and_independent_upgrade_preserve_unrelated_packages_and_data(tmp_path, deb, signing):
    repository = tmp_path / "repository"
    compose([deb("claw-app-alpha"), deb("claw-app-beta")], repository, signing, initialize=True)
    apt = IsolatedApt(tmp_path / "root", repository, signing)
    state = apt.root / "home/owner/.local/share/claw/apps/alpha/state.json"
    state.parent.mkdir(parents=True)
    state.write_bytes(b'{"private":"unchanged state and grant IDs"}\n')
    state.chmod(0o600)
    before = state.stat()
    apt.update()
    apt.call("install", "-y", "claw-app-alpha", "claw-app-beta")
    assert apt.installed("claw-app-alpha") == apt.installed("claw-app-beta") == "1.0.0"
    upgraded = compose([deb("claw-app-alpha", "1.1.0", b"upgraded alpha\n")],
                       tmp_path / "next", signing, previous=repository)
    shutil.rmtree(repository)
    upgraded.rename(repository)
    apt.update()
    apt.call("install", "--only-upgrade", "-y", "claw-app-alpha")
    assert apt.installed("claw-app-alpha") == "1.1.0"
    assert apt.installed("claw-app-beta") == "1.0.0"
    assert (apt.root / "usr/share/clawos-fixture/claw-app-alpha.txt").read_bytes() == b"upgraded alpha\n"
    assert (apt.root / "usr/share/clawos-fixture/claw-app-beta.txt").read_bytes() == b"first payload\n"
    assert state.read_bytes() == b'{"private":"unchanged state and grant IDs"}\n'
    assert state.stat().st_ino == before.st_ino and state.stat().st_mode == before.st_mode


def test_same_version_changed_bytes_and_version_regressions_are_refused(tmp_path, deb, signing):
    first = compose([deb(version="2.0.0")], tmp_path / "first", signing, initialize=True)
    with pytest.raises(ValueError, match="collision"):
        compose([deb(version="2.0.0", payload=b"mutated version")],
                tmp_path / "collision", signing, previous=first)
    with pytest.raises(ValueError, match="regression"):
        compose([deb(version="1.9.9")], tmp_path / "downgrade", signing, previous=first)
    assert not (tmp_path / "collision").exists()
    assert not (tmp_path / "downgrade").exists()


def test_published_version_cannot_regress_on_the_other_architecture(tmp_path, deb, signing):
    first = compose([deb(version="2.0.0", architecture="amd64")],
                    tmp_path / "first", signing, initialize=True)
    with pytest.raises(ValueError, match="regression"):
        compose([deb(version="1.0.0", architecture="arm64")], tmp_path / "regression", signing, previous=first)


def test_changed_pool_bytes_and_changed_metadata_do_not_become_an_empty_repository(tmp_path, deb, signing):
    first = compose([deb()], tmp_path / "first", signing, initialize=True)
    package = next((first / "pool").rglob("*.deb"))
    package.write_bytes(package.read_bytes() + b"substituted payload")
    with pytest.raises(ValueError, match="digest"):
        compose([], tmp_path / "bad-payload", signing, previous=first)
    second = compose([deb("claw-app-second")], tmp_path / "second", signing, initialize=True)
    (second / "dists/trixie/Release").write_text("not a signed Release")
    with pytest.raises(ValueError, match="disagree"):
        compose([], tmp_path / "bad-release", signing, previous=second)


def test_wrong_signatures_and_unsigned_repositories_are_rejected_by_real_apt(tmp_path, deb, signing):
    repository = compose([deb()], tmp_path / "repository", signing, initialize=True)
    signature = repository / "dists/trixie/InRelease"
    data = signature.read_bytes().replace(b"Claw OS Applications", b"Untrusted Replaced!!", 1)
    signature.write_bytes(data)
    with pytest.raises(subprocess.CalledProcessError):
        verify_repository(repository, signing)
    apt = IsolatedApt(tmp_path / "bad-signature-root", repository, signing)
    assert apt.update(check=False).returncode != 0
    signature.unlink()
    (repository / "dists/trixie/Release.gpg").unlink()
    unsigned = IsolatedApt(tmp_path / "unsigned-root", repository, signing)
    assert unsigned.update(check=False).returncode != 0


def test_real_apt_rejects_mutated_package_even_with_valid_repository_metadata(tmp_path, deb, signing):
    repository = compose([deb()], tmp_path / "repository", signing, initialize=True)
    apt = IsolatedApt(tmp_path / "root", repository, signing)
    apt.update()
    package = next((repository / "pool").rglob("*.deb"))
    package.write_bytes(package.read_bytes() + b"changed")
    result = apt.call("install", "-y", "claw-app-fixture", check=False)
    assert result.returncode != 0
    assert not (apt.root / "usr/share/clawos-fixture/claw-app-fixture.txt").exists()


def test_stale_metadata_is_rejected_by_verifier_and_real_apt_and_cannot_be_refreshed_silently(tmp_path, deb, signing):
    repository = compose([deb()], tmp_path / "repository", signing, initialize=True,
                         now=now_utc() - timedelta(days=15))
    with pytest.raises(ValueError, match="stale"):
        verify_repository(repository, signing)
    with pytest.raises(ValueError, match="stale"):
        compose([], tmp_path / "new", signing, previous=repository)
    apt = IsolatedApt(tmp_path / "root", repository, signing)
    assert apt.update(check=False).returncode != 0


def test_authenticated_refresh_changes_freshness_without_rebuilding_any_app(tmp_path, deb, signing):
    repository = compose([deb()], tmp_path / "repository", signing, initialize=True,
                         now=now_utc() - timedelta(days=4))
    before = verify_repository(repository, signing)
    refreshed = compose([], tmp_path / "refreshed", signing, previous=repository)
    assert verify_repository(refreshed, signing) == before
    assert digest(repository / "dists/trixie/Release") != digest(refreshed / "dists/trixie/Release")
    for record in before["packages"]:
        assert digest(repository / record["filename"]) == digest(refreshed / record["filename"])


def test_initial_repository_requires_explicit_initialization_and_cannot_replace_previous(tmp_path, deb, signing):
    with pytest.raises(ValueError, match="initialization"):
        compose([deb()], tmp_path / "repository", signing)
    repository = compose([deb("claw-app-other")], tmp_path / "repository", signing, initialize=True)
    with pytest.raises(ValueError, match="initialize"):
        compose([], tmp_path / "reset", signing, previous=repository, initialize=True)


@pytest.mark.parametrize(("former", "target", "symlink"), [
    ("claw-os-agent", "usr/lib/cos/apps/fixture/entry.py", False),
    ("claw-os-desktop", "usr/bin/claw-applet-calendar", True),
    ("claw-os-desktop", "usr/bin/claw-applet-clipboard", True),
    ("claw-os-desktop", "usr/bin/claw-applet-widget-rail", True),
])
def test_bound_file_ownership_transfer_refuses_a_post_split_os_package(tmp_path, deb, signing, former, target, symlink):
    bound = "1:0.3.0"
    root = tmp_path / "root"
    (root / "var/lib/dpkg").mkdir(parents=True)
    (root / "var/lib/dpkg/status").write_text("")
    private = root / "var/lib/cos/owners/1000/grants.json"
    private.parent.mkdir(parents=True)
    private.write_bytes(b"unchanged exact identity grants")
    install = ["dpkg", "--force-not-root", f"--root={root}", f"--log={root}/dpkg.log", "--install"]
    environment = {"PATH": os.environ["PATH"] + ":/usr/sbin:/sbin"}
    old = deb(former, "1:0.2.0", files=(
        {"usr/bin/cosmic-applets": b"old shared host fixture"} if symlink else {target: b"old bundled client"}
    ), symlinks={target: "cosmic-applets"} if symlink else None)
    run([*install, old], env=environment)
    assert (root / target).is_symlink() == symlink
    app = deb("claw-app-transfer", extra={
        "Breaks": f"{former} (<< {bound})", "Replaces": f"{former} (<< {bound})",
    }, files={target: b"independent client"})
    assert run([*install, app], check=False, env=environment).returncode != 0
    platform = deb(former, bound, files={"usr/share/clawos-fixture/platform": b"OS interfaces only"})
    run([*install, platform], env=environment)
    run([*install, app], env=environment)
    assert (root / target).read_bytes() == b"independent client"
    assert not (root / target).is_symlink()
    assert private.read_bytes() == b"unchanged exact identity grants"
    later = deb(former, "1:0.5.0", files={target: b"unrelated new OS file"})
    assert run([*install, later], check=False, env=environment).returncode != 0


def test_actual_app_catalog_metadata_survives_signed_apt_indexing(tmp_path, signing):
    plan = release.make_plan("capability:storage-sdk", "1.2.3")
    release.build(plan, "all", tmp_path / "packages")
    repository = compose(sorted((tmp_path / "packages").glob("*.deb")),
                         tmp_path / "repository", signing, initialize=True)
    apt = IsolatedApt(tmp_path / "root", repository, signing)
    apt.update()
    record = fields(run(["apt-cache", "show", "claw-cap-storage-sdk"], env={
        "APT_CONFIG": str(apt.configuration),
    }).stdout.decode().strip())
    assert record["Version"] == "1.2.3"
    assert record["X-Claw-Product"] == "storage-sdk"
    assert record["X-Claw-Source-Kind"] == "capability"
    assert record["X-Claw-Variant"] == "agent"
    assert record["X-Claw-App-Ids"] == "db, kv"
