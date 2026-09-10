"""Publish immutable App Releases and a separately authenticated APT snapshot."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time

from release import load_plan
from release_apt import compose, verify_repository
from release_common import (
    ROOT, command_environment, compare_versions, config, digest, identity, json_bytes, package_record,
    relative_path, run, version, work_path, write_json,
)
from release_signing import Signing
from release_development import verify_archive


class GitHub:
    def __init__(self):
        self.settings = config()
        self.repository = self.settings["repository"]
        if os.environ.get("GITHUB_REPOSITORY", self.repository) != self.repository:
            raise ValueError("App publication cannot target another repository")

    def api(self, endpoint, *, method="GET", data=None, allowed=(200,)):
        arguments = [
            "gh", "api", "--hostname", "github.com", "--include",
            "--header", "Accept: application/vnd.github+json",
            "--header", "X-GitHub-Api-Version: 2026-03-10", "--method", method,
            f"repos/{self.repository}/{endpoint}".rstrip("/"),
        ]
        payload = None
        if data is not None:
            arguments.extend(["--input", "-"])
            payload = json_bytes(data)
        response = run(arguments, input=payload, check=False)
        parts = re.split(rb"\r?\n\r?\n", response.stdout, maxsplit=1)
        status = re.match(rb"HTTP/\S+\s+([0-9]{3})", parts[0])
        if not status or len(parts) != 2:
            raise ValueError("GitHub transport failed; no authenticated HTTP response")
        code = int(status[1])
        if code not in allowed or (response.returncode and code < 400):
            raise ValueError(f"GitHub {method} {endpoint} failed with HTTP {code}")
        return code, json.loads(parts[1]) if parts[1].strip() else None

    def preflight(self):
        _, repository = self.api("")
        if repository.get("full_name", "").lower() != self.repository.lower() or repository.get("private"):
            raise ValueError("The signed App Pages channel requires its declared public repository")
        _, immutable = self.api("immutable-releases")
        if immutable.get("enabled") is not True:
            raise ValueError("Enable immutable releases in the App repository before publishing")


def release_tag(selection, release_version):
    prefix = "cap-" + selection.removeprefix("capability:") if selection.startswith("capability:") else (
        selection if selection in ("support", "sets") else "app-" + selection
    )
    return f"{prefix}-v{release_version.replace('~', '-')}"


def require_publication_contract(settings):
    if settings.get("integration_contract") != "verified-origin-neutral-app-host":
        raise ValueError(
            "New App publication is blocked pending the generic authenticated App Host/capability/"
            "resource-owner contract; existing protections must not be bypassed. See docs/releases.md."
        )


def verify_artifacts(plan, directory):
    expected = {
        f"{entry['package']}_{plan['version']}_{entry['architecture']}.deb": entry
        for entry in plan["packages"]
    }
    packages = sorted(directory.glob("*.deb"))
    if {path.name for path in packages} != set(expected):
        raise ValueError("Release artifacts do not exactly cover the selected packages and architectures")
    records = {path.name: package_record(path) for path in packages}
    for name, record in records.items():
        entry = expected[name]
        control = record["control"]
        if control.get("X-Claw-Source-Revision") != plan["source_revision"] or (
            control.get("X-Claw-Variant") != entry["variant"]
        ) or control.get("X-Claw-App-Ids", "") != ", ".join(entry["apps"]):
            raise ValueError("Release artifact metadata does not match the tested plan")
    jobs = {job["architecture"] for job in plan["matrix"]["include"]}
    development = {}
    if {path.name for path in directory.glob("build-record-*.json")} != {
        f"build-record-{architecture}.json" for architecture in jobs
    }:
        raise ValueError("A matrix build record is missing")
    for architecture in jobs:
        report = json.loads((directory / f"build-record-{architecture}.json").read_text())
        wanted = [record for record in records.values() if record["architecture"] == architecture]
        if report.get("format") != "claw.app-build/v1" or report.get("plan") != plan or (
            sorted(report["packages"], key=identity) != sorted(wanted, key=identity)
        ):
            raise ValueError("Matrix build records differ from the Debian artifacts")
        if report.get("interfaces", {}) != {}:
            raise ValueError("Retired App config/util interface archives are not release inputs")
        if architecture == "all":
            development = report.get("development", {})
            if set(development) != (set(plan["selections"]) if plan["include_fixtures"] else set()):
                raise ValueError("A selected development fixture archive is missing")
            for selection, record in development.items():
                if record.get("selection") != selection:
                    raise ValueError("Development archive selection mismatch")
                verify_archive(directory / relative_path(record["filename"]), record, plan)
        elif report.get("development"):
            raise ValueError("Architecture-independent fixture archives must be built once")
    if {path.name for path in directory.glob("*.tar.xz")} != {record["filename"] for record in development.values()}:
        raise ValueError("Unexpected or missing development fixture archives")
    if any(directory.glob("*.tar.gz")):
        raise ValueError("Retired App interface archives are not accepted as Debian release inputs")
    return packages, development, {}


def assert_initial_publication(github):
    page = 1
    while True:
        _, releases = github.api(f"releases?per_page=100&page={page}")
        if any(re.match(r"(?:app-|cap-|support-v|sets-v)", release["tag_name"]) for release in releases):
            raise ValueError("Prior App releases exist: restore the authenticated APT state, do not initialize")
        if len(releases) < 100:
            return
        page += 1


def previous_snapshot(github, destination, *, initialize):
    branch = github.settings["state_branch"]
    status, reference = github.api(f"git/ref/heads/{branch}", allowed=(200, 404))
    if status == 404:
        if not initialize:
            raise ValueError("APT state branch is absent; first publication requires --initialize")
        assert_initial_publication(github)
        return None, None
    if initialize:
        raise ValueError("APT state already exists; initialization is forbidden")
    commit = reference["object"]["sha"]
    if reference["object"]["type"] != "commit" or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid APT state reference")
    run(["git", "fetch", "--no-tags", "--depth=1", "origin", commit])
    destination = work_path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    # Extract the exact fetched commit, not a later mutable branch response.
    process = subprocess.Popen(
        ["git", "archive", "--format=tar", commit], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=command_environment(),
    )
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                relative = relative_path(member.name.rstrip("/"))
                if relative.parts[0] == ".git" or not (member.isdir() or member.isfile()):
                    raise ValueError("Unsafe APT state archive entry")
                path = destination / relative
                if member.isdir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as source, path.open("xb") as target:
                        shutil.copyfileobj(source, target)
        _, errors = process.communicate()
        if process.returncode:
            raise ValueError(f"Cannot read authenticated APT state commit: {errors.decode()}")
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
        process.stderr.close()
    return destination, commit


def release_assets(plan, selection, packages, directory, signing, *, development, artifact_directory, interfaces=None):
    if interfaces not in (None, {}):
        raise ValueError("Retired App config/util interface archives cannot be signed or published")
    target = directory / release_tag(selection, plan["version"])
    target.mkdir(parents=True)
    names = {
        entry["package"] for entry in plan["packages"] if entry["selection"] == selection
    }
    selected = []
    for package in packages:
        record = package_record(package)
        if record["package"] in names:
            shutil.copy2(package, target / package.name)
            if package_record(target / package.name) != record:
                raise ValueError("Debian release payload changed while preparing immutable assets")
            selected.append(record)
    fixture = development.get(selection)
    if fixture:
        archive = artifact_directory / fixture["filename"]
        verify_archive(archive, fixture, plan)
        shutil.copy2(archive, target / archive.name)
        verify_archive(target / archive.name, fixture, plan)
    write_json(target / "release.json", {
        "format": "claw.app-release-assets/v1", "selection": selection,
        "version": plan["version"], "source_revision": plan["source_revision"],
        "packages": sorted(selected, key=identity),
        "development": fixture,
        "interfaces": None,
    })
    sums = "".join(f"{digest(path)}  {path.name}\n" for path in sorted(target.iterdir()))
    (target / "SHA256SUMS").write_text(sums)
    signing.sign(target / "SHA256SUMS", target / "SHA256SUMS.asc", armored=True)
    return target


def existing_release(github, tag, revision):
    status, release = github.api(f"releases/tags/{tag}", allowed=(200, 404))
    tag_status, reference = github.api(f"git/ref/tags/{tag}", allowed=(200, 404))
    if tag_status == 200 and (
        reference["object"]["type"] != "commit" or reference["object"]["sha"] != revision
    ):
        raise ValueError(f"Refusing to rebind an existing release tag: {tag}")
    if status == 404:
        if tag_status == 200:
            raise ValueError(f"An existing tag has no completed release: {tag}; use a new version")
        return None
    if tag_status != 200 or release.get("draft") or release.get("immutable") is not True:
        raise ValueError(f"An existing release is not a completed immutable release: {tag}")
    return release


def check_published_versions(github, selections, requested):
    prefixes = {release_tag(selection, ""): selection for selection in selections}
    page = 1
    while True:
        _, releases = github.api(f"releases?per_page=100&page={page}")
        for published in releases:
            if published.get("draft") or not published.get("immutable"):
                continue
            for prefix, selection in prefixes.items():
                if not published["tag_name"].startswith(prefix):
                    continue
                candidate = published["tag_name"].removeprefix(prefix)
                candidate = re.sub(r"^([0-9]+\.[0-9]+\.[0-9]+)-(alpha|beta|rc)", r"\1~\2", candidate)
                version(candidate)
                if compare_versions(candidate, "gt", requested):
                    raise ValueError(f"A newer immutable release exists for {selection}; version regression refused")
        if len(releases) < 100:
            return
        page += 1


def publish_release(github, tag, revision, assets, existing, signing, *, prerelease=False):
    if existing:
        names = {path.name for path in assets.iterdir()}
        if {asset["name"] for asset in existing["assets"]} != names:
            raise ValueError(f"Existing immutable release has different assets: {tag}")
        downloaded = assets.parent / f"{tag}-verified"
        downloaded.mkdir()
        try:
            run(["gh", "release", "download", tag, "--repo", github.repository, "--dir", downloaded])
            signing.verify(downloaded / "SHA256SUMS.asc", downloaded / "SHA256SUMS")
            for name in names - {"SHA256SUMS.asc"}:
                if digest(downloaded / name) != digest(assets / name):
                    raise ValueError(f"Immutable release version collision: {tag}/{name}")
        finally:
            shutil.rmtree(downloaded)
        return
    github.api("git/refs", method="POST", data={"ref": f"refs/tags/{tag}", "sha": revision}, allowed=(201,))
    _, draft = github.api("releases", method="POST", allowed=(201,), data={
        "tag_name": tag, "target_commitish": revision, "draft": True, "name": tag,
        "prerelease": prerelease,
        "body": f"Signed Debian App packages. Source commit: {revision}. "
                "SHA256SUMS is signed by the separately pinned App archive key.",
    })
    run([
        "gh", "release", "upload", tag, "--repo", github.repository,
        *(path for path in sorted(assets.iterdir())),
    ])
    _, published = github.api(f"releases/{draft['id']}", method="PATCH",
                              data={"draft": False, "make_latest": "false"})
    if published.get("immutable") is not True:
        raise ValueError("GitHub did not lock the release; refusing APT publication")
    existing_release(github, tag, revision)


def check_hosting_limits(output):
    for path in output.rglob("*.deb"):
        if path.stat().st_size >= 100_000_000:
            raise ValueError("A .deb exceeds GitHub's state-branch blob limit; do not publish a truncated package")
    if sum(path.stat().st_size for path in output.rglob("*") if path.is_file()) >= 1_000_000_000:
        raise ValueError("Retained APT content exceeds the Pages size limit; no packages were silently discarded")


def push_snapshot(github, output, previous_commit):
    run(["git", "init", "--quiet", "--initial-branch", github.settings["state_branch"]], cwd=output)
    try:
        run(["git", "remote", "add", "origin", f"https://github.com/{github.repository}.git"], cwd=output)
        if previous_commit:
            run(["git", "fetch", "--quiet", "--no-tags", "--depth=1", "origin", previous_commit], cwd=output)
            run(["git", "update-ref", "HEAD", previous_commit], cwd=output)
        run(["git", "add", "--", ".nojekyll", "archive-key.asc", "index.html", "pool", "dists"], cwd=output)
        run(["git", "-c", "user.name=Claw OS Applications Release",
             "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
             "commit", "--quiet", "--message", "Publish authenticated App APT metadata"], cwd=output)
        # An ordinary fast-forward push is also the publication compare-and-swap.
        run(["git", "push", "--quiet", "origin", f"HEAD:refs/heads/{github.settings['state_branch']}"], cwd=output)
    finally:
        shutil.rmtree(output / ".git")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    publishing = commands.add_parser("publish")
    publishing.add_argument("--plan", type=Path, required=True)
    publishing.add_argument("--artifacts", type=Path, required=True)
    publishing.add_argument("--initialize", action="store_true")
    for action in (publishing, commands.add_parser("refresh")):
        action.add_argument("--output", type=Path, default=ROOT / "build/apt-publication")
    options = parser.parse_args()
    if options.command == "publish":
        require_publication_contract(config())
    if os.environ.get("GITHUB_REF", "refs/heads/main") != "refs/heads/main":
        raise ValueError("Release and refresh workflows only publish reviewed main-branch code")
    if run(["git", "status", "--porcelain", "--untracked-files=normal"]).stdout:
        raise ValueError("Publication requires a clean, committed App source checkout")
    github = GitHub()
    github.preflight()
    output = work_path(options.output)
    plan = load_plan(options.plan) if options.command == "publish" else None
    packages, development, interfaces = verify_artifacts(plan, options.artifacts) if plan else ([], {}, {})
    previous, commit = previous_snapshot(
        github, output.parent / "apt-previous",
        initialize=options.command == "publish" and options.initialize,
    )
    try:
        with Signing(output.parent / "apt-publish-signing") as signing:
            if previous:
                verify_repository(previous, signing)
            signing.import_environment()
            compose(packages, output, signing, previous=previous, initialize=previous is None)
            check_hosting_limits(output)
            if plan:
                check_published_versions(github, plan["selections"], plan["version"])
                assets_root = output.parent / "immutable-app-releases"
                assets_root.mkdir()
                try:
                    existing = {
                        selection: existing_release(github, release_tag(selection, plan["version"]),
                                                    plan["source_revision"])
                        for selection in plan["selections"]
                    }
                    previous_write = 0.0
                    for selection in plan["selections"]:
                        assets = release_assets(plan, selection, packages, assets_root, signing,
                                                development=development, artifact_directory=options.artifacts,
                                                interfaces=interfaces)
                        if not existing[selection]:
                            # Bound small-package batches below GitHub's content-creation rate limit.
                            time.sleep(max(0, 9 - (time.monotonic() - previous_write)))
                            previous_write = time.monotonic()
                        publish_release(github, release_tag(selection, plan["version"]),
                                        plan["source_revision"], assets, existing[selection], signing,
                                        prerelease="~" in plan["version"])
                finally:
                    shutil.rmtree(assets_root)
            push_snapshot(github, output, commit)
            verify_repository(output, signing)
    finally:
        if previous:
            shutil.rmtree(previous)
    print(f"Verified signed App APT snapshot ready for Pages: {output}")


if __name__ == "__main__":
    main()
