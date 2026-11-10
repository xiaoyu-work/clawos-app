from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

import release_apt
import release_publish
import release_store as store
import release_snapshots as snapshots
from release_common import digest, json_bytes, package_record, run, write_json
from test_snapshots import runtime, app


def web_app(root):
    (root / "LICENSE").chmod(0o644)
    (root / "web").mkdir()
    (root / "web/index.html").write_text("<!doctype html><title>Store fixture</title>")
    (root / "web/app.js").write_text("window.fixture = true;")
    manifest = snapshots.read_metadata(root / "app.json")
    write_json(root / "web-ui.json", {
        "schema": "claw.web-app/v1", "app_id": manifest["id"], "source_kind": "product",
        "source_name": "fixture", "title": manifest["name"], "description": "",
        "entry": "web/index.html",
    })
    return root


@pytest.fixture
def public_signer(tmp_path, monkeypatch):
    """Fake the public CLI wire only; real signature integration remains in runtime."""
    binary = tmp_path / "fake-public-cos"
    binary.write_text("test-only public signer fixture; not a production executable\n")
    binary.chmod(0o755)
    key = tmp_path / "package-key.json"
    write_json(key, {"test_only": True})
    publisher = "sha256:" + "a" * 64
    issued = {}

    def inventory(root):
        return {name: record for name, record in snapshots.tree_inventory(root, "all").items()
                if name != ".provenance.json"}

    def execute(arguments, **kwargs):
        assert Path(arguments[0]) == binary
        root = Path(arguments[arguments.index("--path") + 1])
        if arguments[2] == "sign":
            assert Path(arguments[arguments.index("--key") + 1]) == key
            manifest = snapshots.read_metadata(root / "app.json")
            entries = [str(arguments[index + 1]) for index, value in enumerate(arguments)
                       if value == "--entrypoint"]
            files = [{"path": name, "type": "file", "size": record["size"],
                      "digest": "sha256:" + record["sha256"]}
                     for name, record in inventory(root).items() if record["type"] == "file"]
            envelope = {
                "schema": "claw.provenance/v1",
                "package": {
                    "kind": "app", "id": manifest["id"], "version": manifest["version"],
                    "manifest_schema": "cos.app-manifest/v1", "manifest_path": "app.json",
                    "entrypoints": entries, "files": files, "content_digest": "sha256:" + "b" * 64,
                },
                "signature": {"algorithm": "ed25519", "key_id": publisher,
                              "value": f"test-only-issued-envelope-{len(issued)}"},
            }
            write_json(root / ".provenance.json", envelope)
            issued[digest(root / ".provenance.json")] = inventory(root)
            value = {"signed": True}
        else:
            assert arguments[2] == "verify"
            envelope_path = root / ".provenance.json"
            if not envelope_path.is_file() or issued.get(digest(envelope_path)) != inventory(root):
                return subprocess.CompletedProcess(arguments, 1, b'{"error":"fixture bytes changed"}', b"")
            envelope = snapshots.read_metadata(envelope_path)
            value = {
                "verified": True, "manifest_path": "app.json",
                "entrypoints": envelope["package"]["entrypoints"],
                "package": {**envelope["package"], "trust": "publisher", "publisher_key_id": publisher},
            }
        return subprocess.CompletedProcess(arguments, 0, json_bytes(value), b"")

    monkeypatch.setattr(snapshots, "run", execute)
    verifier = snapshots.Provenance(binary, digest(binary), publisher)

    def sign(root):
        manifest = snapshots.read_metadata(root / "app.json")
        arguments = [binary, "provenance", "sign", "--kind", "app", "--id", manifest["id"],
                     "--version", manifest["version"], "--path", root, "--key", key]
        for _, entry in snapshots.manifest_entries(manifest):
            arguments.extend(("--entrypoint", entry))
        execute(arguments)
        return root

    return verifier, sign


def app_deb(deb, roots, *, version="1.0.0", architecture="all", extra=None, control_files=None, symlinks=None):
    files, modes, apps = {}, {}, []
    for root in roots:
        value = snapshots.read_metadata(root / "app.json")["id"]
        apps.append(value)
        base = f"usr/lib/cos/apps/{value}"
        modes[base] = root.stat().st_mode & 0o777
        for path in root.rglob("*"):
            name = base + "/" + path.relative_to(root).as_posix()
            modes[name] = path.stat().st_mode & 0o777
            if path.is_file():
                files[name] = path.read_bytes()
    return deb("claw-app-fixture", version, architecture=architecture, files=files, modes=modes,
               control_files=control_files, symlinks=symlinks,
               extra={"X-Claw-App-Ids": ", ".join(apps), "X-Claw-Product": "fixture",
                      "X-Claw-Source-Kind": "product", "X-Claw-Variant": "agent",
                      "X-Claw-Source-Revision": "a" * 40, **(extra or {})})


def test_store_index_binds_signed_product_ui_and_immutable_release(tmp_path, public_signer, signing, app, deb):
    verifier, sign = public_signer
    root = sign(web_app(app()))
    snapshots.build_catalog([root], tmp_path / "snapshots", release_version="1.0.0",
                            architecture="all", provenance=verifier, signing=signing)
    package = app_deb(deb, [root])
    index = store.compose([tmp_path / "snapshots"], tmp_path / "store", verifier, signing, packages=[package])
    record = index["apps"][0]
    assert record["web_ui"]["sha256"] == digest(root / "web-ui.json")
    assert record["release_tag"] == "app-fixture-v1.0.0"
    assert record["artifact"]["sha256"] in record["artifact"]["file"]
    assert record["delivery"] == {"kind": "apt", "package_sha256": digest(package)}
    assert store.verified_index(tmp_path / "store", signing) == index
    assert "permissions_granted" not in json.dumps(index)
    changed = dict(index)
    changed["expires_at"] = store.utc(datetime.now(timezone.utc) - timedelta(seconds=1))
    with pytest.raises(ValueError, match="freshness|expired"):
        store.validate_index(changed)
    changed = json.loads(json.dumps(index))
    changed["apps"][0]["release_tag"] = "app-different-v1.0.0"
    with pytest.raises(ValueError, match="official release"):
        store.validate_index(changed)
    (tmp_path / "store/index.json").write_text("{}")
    with pytest.raises(subprocess.CalledProcessError):
        store.verified_index(tmp_path / "store", signing)


def test_store_refresh_keeps_artifacts_and_advances_signed_freshness(tmp_path, public_signer, signing, app, deb):
    verifier, sign = public_signer
    root = sign(web_app(app()))
    snapshots.build_catalog([root], tmp_path / "snapshots", release_version="1.0.0",
                            architecture="all", provenance=verifier, signing=signing)
    initial = store.compose([tmp_path / "snapshots"], tmp_path / "store", verifier, signing,
                            packages=[app_deb(deb, [root])])
    refreshed = store.refresh(tmp_path / "store", signing)
    assert refreshed["apps"] == initial["apps"]
    assert refreshed["packages"] == initial["packages"]
    assert int(refreshed["generation"]) > int(initial["generation"])
    assert store.verified_index(tmp_path / "store", signing) == refreshed


def test_publication_signs_exact_debian_app_payload_and_retains_web_assets(
    tmp_path, runtime, signing, app, deb,
):
    verifier, _ = runtime
    root = web_app(app())
    app_id = snapshots.read_metadata(root / "app.json")["id"]
    artifact = app_deb(deb, [root])
    plan = {"version": "1.0.0", "source_date_epoch": 1700000000, "packages": [{
        "package": "claw-app-fixture", "architecture": "all",
        "selection": "fixture", "apps": [app_id],
    }]}
    packages, groups = store.prepare_release_snapshots(
        plan, [artifact], tmp_path / "prepared", verifier, signing,
        tmp_path / "package-key.json",
    )
    record = store.snapshot_records(groups["fixture"][0], verifier, signing)[0]
    extracted = tmp_path / "extracted"
    snapshots.extract_archive(groups["fixture"][0] / record["artifact"]["file"], extracted)
    assert (extracted / "web/app.js").read_bytes() == (root / "web/app.js").read_bytes()
    assert (extracted / "app.json").read_bytes() == (root / "app.json").read_bytes()
    assert (extracted / ".provenance.json").is_file()
    assert record["provenance"]["publisher_key_id"] == verifier.publisher_key_id
    final = tmp_path / "final"
    run(["dpkg-deb", "--extract", packages[0], final])
    assert (final / f"usr/lib/cos/apps/{app_id}/.provenance.json").read_bytes() == (
        extracted / ".provenance.json"
    ).read_bytes()


@pytest.fixture
def bundle(tmp_path, public_signer, signing, app, deb):
    verifier, _ = public_signer
    roots = [web_app(app("bundle-first")), web_app(app("bundle-second"))]
    (roots[0] / "server.py").chmod(0o755)
    (roots[0] / "LICENSE").chmod(0o444)
    (roots[0] / "web").chmod(0o750)
    package = app_deb(deb, roots, version="1.0.0-2", control_files={"md5sums": b""},
                      symlinks={"usr/share/claw-fixture/license-link": "./../../lib/cos/apps/bundle-first/LICENSE"})
    support = deb("claw-app-support", "1.0.0-2",
                  extra={"X-Claw-Variant": "support", "X-Claw-Source-Revision": "a" * 40},
                  files={"usr/lib/cos/python/fixture.py": b"shared library fixture\n"},
                  symlinks={"usr/lib/cos/python/fixture-link.py": "fixture.py"})
    metapackage = deb("claw-apps-agent", "1.0.0-2",
                      extra={"X-Claw-Variant": "agent", "X-Claw-Source-Revision": "a" * 40})
    plan = {
        "version": "1.0.0-2", "source_date_epoch": 1700000000, "source_revision": "a" * 40,
        "include_fixtures": False, "selections": ["fixture", "support", "sets"],
        "matrix": {"include": [{"architecture": "all"}]},
        "packages": [
            {"package": "claw-app-fixture", "architecture": "all", "variant": "agent",
             "selection": "fixture", "apps": ["bundle-first", "bundle-second"]},
            {"package": "claw-app-support", "architecture": "all", "variant": "support",
             "selection": "support", "apps": []},
            {"package": "claw-apps-agent", "architecture": "all", "variant": "agent",
             "selection": "sets", "apps": []},
        ],
    }
    ci = tmp_path / "ci"
    ci.mkdir()
    for path in (package, support, metapackage):
        shutil.copy2(path, ci / path.name)
    originals = [package_record(path) for path in sorted(ci.glob("*.deb"))]
    write_json(ci / "build-record-all.json", {
        "format": "claw.app-build/v1", "plan": plan, "packages": originals,
        "development": {}, "interfaces": {},
    })
    packages, _, _ = release_publish.verify_artifacts(plan, ci)
    final, groups = store.prepare_release_snapshots(
        plan, packages, tmp_path / "prepared", verifier, signing, tmp_path / "package-key.json",
    )
    index = store.compose(groups["fixture"], tmp_path / "store", verifier, signing, packages=final)
    return plan, originals, final, groups, index, verifier


def test_final_signed_debs_drive_store_snapshots_apt_and_immutable_assets(tmp_path, signing, bundle):
    plan, originals, packages, groups, index, verifier = bundle
    before = {item["package"]: item for item in originals}
    final = {item["package"]: item for item in map(package_record, packages)}
    assert final["claw-app-fixture"]["sha256"] != before["claw-app-fixture"]["sha256"]
    assert final["claw-app-support"] == before["claw-app-support"]
    assert final["claw-apps-agent"] == before["claw-apps-agent"]
    report = snapshots.read_metadata(tmp_path / "prepared/release-record.json")
    assert report["build_packages"] == sorted(originals, key=store.identity)
    assert report["packages"] == sorted(final.values(), key=store.identity)
    release_publish.verify_artifacts(plan, tmp_path / "ci")
    assert {item["package"]: item["apps"] for item in index["packages"]} == {
        "claw-app-fixture": ["bundle-first", "bundle-second"],
        "claw-app-support": [], "claw-apps-agent": [],
    }
    extracted = tmp_path / "final"
    package = next(path for path in packages if path.name.startswith("claw-app-fixture_"))
    run(["dpkg-deb", "--raw-extract", package, extracted])
    assert (extracted / "DEBIAN/control").read_bytes() == (
        tmp_path / "deb-1/stage/DEBIAN/control"
    ).read_bytes()
    assert os.readlink(extracted / "usr/share/claw-fixture/license-link") == "./../../lib/cos/apps/bundle-first/LICENSE"
    sums = (extracted / "DEBIAN/md5sums").read_text()
    for record in store.snapshot_records(groups["fixture"][0], verifier, signing):
        snapshot = tmp_path / record["app_id"]
        snapshots.extract_archive(groups["fixture"][0] / record["artifact"]["file"], snapshot)
        installed = extracted / "usr/lib/cos/apps" / record["app_id"]
        assert snapshots.tree_inventory(installed, "all") == snapshots.tree_inventory(snapshot, "all")
        assert f"{digest(installed / '.provenance.json', 'md5')}  " in sums
        assert f"usr/lib/cos/apps/{record['app_id']}/.provenance.json\n" in sums
    assert not (tmp_path / "entrypoint-executed").exists()
    assert all(record["delivery"] == {"kind": "apt", "package_sha256": final["claw-app-fixture"]["sha256"]}
               for record in index["apps"])
    assert all(record["version"] == "1.0.0-2" for record in index["packages"])
    repository = release_apt.compose(packages, tmp_path / "apt", signing, initialize=True,
                                     store=tmp_path / "store")
    assert release_apt.verify_repository(repository, signing)["packages"] == sorted(final.values(), key=store.identity)
    assets = release_publish.release_assets(
        plan, "fixture", packages, tmp_path / "assets", signing, development={},
        artifact_directory=tmp_path / "ci", snapshots=groups["fixture"], build_packages=originals,
    )
    published = snapshots.read_metadata(assets / "release.json")
    assert published["packages"] == [final["claw-app-fixture"]]
    assert published["build_packages"] == [before["claw-app-fixture"]]
    assert (assets / package.name).read_bytes() == package.read_bytes()
    for field, value in (("size", final["claw-app-fixture"]["size"] + 1), ("sha256", "c" * 64)):
        changed = json.loads(json.dumps(index))
        next(item for item in changed["packages"] if item["package"] == "claw-app-fixture")[field] = value
        if field == "sha256":
            for record in changed["apps"]:
                record["delivery"]["package_sha256"] = value
        write_json(repository / "store/index.json", changed)
        signing.sign(repository / "store/index.json", repository / "store/index.json.asc", armored=True)
        with pytest.raises(ValueError, match="inventory differs"):
            release_apt.verify_repository(repository, signing)


def test_store_v2_rejects_missing_ambiguous_and_conflicting_apt_bindings(bundle):
    _, _, _, _, index, _ = bundle
    mutations = [
        lambda value: value.update(schema="claw.app-store/v1"),
        lambda value: value["packages"].append(dict(value["packages"][0])),
        lambda value: value["packages"][0].update(apps=["bundle-first", "bundle-first"]),
        lambda value: value["apps"][0]["delivery"].update(package_sha256="0" * 64),
        lambda value: value["apps"][0]["delivery"].update(kind="snapshot"),
        lambda value: value["apps"][0]["delivery"].update(fallback="snapshot"),
        lambda value: value["packages"][0].update(architecture="amd64"),
        lambda value: value["packages"][0].update(filename="not-in-the-wire-format.deb"),
        lambda value: value["packages"][1].update(apps=["bundle-first"]),
        lambda value: value["packages"].append({**value["packages"][0], "version": "2.0.0", "sha256": "e" * 64}),
    ]
    for mutate in mutations:
        changed = json.loads(json.dumps(index))
        mutate(changed)
        with pytest.raises(ValueError):
            store.validate_index(changed)


@pytest.mark.parametrize("change", [
    {"size": 1024**3 + 1},
    {"package": "claw-app-" + "a" * 248},
    {"apps": [f"app{number:04}" for number in range(1001)]},
])
def test_store_package_limits_fit_the_os_delivery_parser(change):
    record = {"package": "claw-app-fixture", "version": "1.0.0", "architecture": "all",
              "size": 1, "sha256": "a" * 64, "apps": []}
    with pytest.raises(ValueError):
        store.validate_packages([{**record, **change}])


def test_store_retains_package_tuples_on_support_only_release_and_checks_apt_inventory(
    tmp_path, bundle, signing, deb,
):
    _, _, packages, _, initial, _ = bundle
    support = deb("claw-app-support", "2.0.0")
    retained = store.compose([], tmp_path / "retained", None, signing, packages=[support],
                             previous=tmp_path / "store")
    assert retained["apps"] == initial["apps"]
    for record in initial["packages"]:
        assert record in retained["packages"]
    assert len(retained["packages"]) == len(initial["packages"]) + 1
    with pytest.raises(ValueError, match="tuple collision"):
        store.compose([], tmp_path / "collision", None, signing,
                      packages=[deb("claw-app-support", "1.0.0-2", payload=b"different bytes")],
                      previous=tmp_path / "store")
    with pytest.raises(ValueError, match="inventory differs"):
        release_apt.compose(packages, tmp_path / "incomplete", signing, initialize=True,
                            store=tmp_path / "retained")
    old = release_apt.compose(packages, tmp_path / "old-apt", signing, initialize=True,
                              store=tmp_path / "store")
    updated = release_apt.compose([support], tmp_path / "new-apt", signing, previous=old,
                                  store=tmp_path / "retained")
    assert store.verified_index(updated / "store", signing) == retained
    with pytest.raises(ValueError, match="downgrade"):
        store.compose([], tmp_path / "downgrade", None, signing,
                      packages=[deb("claw-app-support", "1.9.9")], previous=tmp_path / "retained")


@pytest.mark.parametrize("mismatch", ["control", "ownership", "signature", "snapshot"])
def test_store_rejects_control_provenance_and_snapshot_mismatches(
    tmp_path, public_signer, signing, app, deb, mismatch,
):
    verifier, sign = public_signer
    root = sign(web_app(app()))
    snapshots.build_catalog([root], tmp_path / "snapshots", release_version="1.0.0",
                            architecture="all", provenance=verifier, signing=signing)
    extra = {}
    if mismatch == "control":
        extra["X-Claw-App-Ids"] = "different-app"
        message = "control App IDs"
    elif mismatch == "ownership":
        extra["X-Claw-Source-Kind"] = "capability"
        message = "source ownership"
    elif mismatch == "signature":
        (root / ".provenance.json").write_text("{}")
        message = "provenance verification failed"
    else:
        (root / "web/app.js").write_text("different, independently authenticated bytes\n")
        sign(root)
        message = "Snapshot bytes differ"
    package = app_deb(deb, [root], extra=extra)
    with pytest.raises(ValueError, match=message):
        store.compose([tmp_path / "snapshots"], tmp_path / "store", verifier, signing, packages=[package])
    assert not (tmp_path / "store").exists()


def test_delivery_validation_runs_on_final_repacked_deb(
    tmp_path, public_signer, signing, app, deb, monkeypatch,
):
    verifier, _ = public_signer
    package = app_deb(deb, [web_app(app())])
    original = store.run

    def inject_hook(arguments, **kwargs):
        if "--build" in arguments:
            root = Path(arguments[arguments.index("--build") + 1])
            (root / "DEBIAN/postinst").write_text("#!/bin/sh\nexit 0\n")
            (root / "DEBIAN/postinst").chmod(0o755)
        return original(arguments, **kwargs)

    monkeypatch.setattr(store, "run", inject_hook)
    plan = {"version": "1.0.0", "source_date_epoch": 1700000000, "packages": [{
        "package": "claw-app-fixture", "architecture": "all",
        "selection": "fixture", "apps": ["snapshot-fixture"],
    }]}
    with pytest.raises(ValueError, match="maintainer/root hooks"):
        store.prepare_release_snapshots(
            plan, [package], tmp_path / "prepared", verifier, signing, tmp_path / "package-key.json",
        )
    assert not (tmp_path / "prepared").exists()


@pytest.mark.parametrize("architecture", ["amd64", "arm64"])
def test_debian_architecture_binding_is_exact(tmp_path, public_signer, signing, app, deb, architecture):
    verifier, _ = public_signer
    package = app_deb(deb, [web_app(app())], architecture=architecture)
    plan = {"version": "1.0.0", "source_date_epoch": 1700000000, "packages": [{
        "package": "claw-app-fixture", "architecture": architecture,
        "selection": "fixture", "apps": ["snapshot-fixture"],
    }]}
    packages, groups = store.prepare_release_snapshots(
        plan, [package], tmp_path / "prepared", verifier, signing, tmp_path / "package-key.json",
    )
    index = store.compose(groups["fixture"], tmp_path / "store", verifier, signing, packages=packages)
    assert index["apps"][0]["architecture"] == index["packages"][0]["architecture"] == architecture
    assert index["apps"][0]["delivery"]["package_sha256"] == digest(packages[0])


def test_publisher_hands_final_signed_bytes_to_indexes_assets_and_state(
    tmp_path, bundle, signing, monkeypatch,
):
    plan, originals, packages, groups, _, verifier = bundle
    events = []
    compose_store, compose_apt = store.compose, release_publish.compose
    make_assets = release_publish.release_assets
    push_state = release_publish.push_snapshot

    def prepare(plan, inputs, output, *args):
        events.append("authenticate")
        assert {digest(path) for path in inputs} == {record["sha256"] for record in originals}
        write_json(output / "release-record.json", {"build_packages": originals})
        return packages, groups

    def store_index(*args, **kwargs):
        events.append("store")
        assert kwargs["packages"] == packages
        return compose_store(*args, **kwargs)

    def apt_index(inputs, *args, **kwargs):
        events.append("apt")
        assert inputs == packages
        assert (kwargs["store"] / "index.json").is_file()
        return compose_apt(inputs, *args, **kwargs)

    def assets(plan, selection, inputs, *args, **kwargs):
        events.append("assets")
        assert inputs == packages and kwargs["build_packages"] == originals
        return make_assets(plan, selection, inputs, *args, **kwargs)

    def no_git(arguments, **kwargs):
        assert arguments == ["git", "status", "--porcelain", "--untracked-files=normal"]
        return subprocess.CompletedProcess(arguments, 0, b"", b"")

    def state(github, output, previous):
        events.append("state")
        assert previous is None
        assert store.verified_index(output / "store", signing)["packages"]
        commands = []

        def fake_git(arguments, **kwargs):
            commands.append(arguments)
            if arguments[:2] == ["git", "init"]:
                (output / ".git").mkdir()
            return subprocess.CompletedProcess(arguments, 0, b"", b"")

        with monkeypatch.context() as context:
            context.setattr(release_publish, "run", fake_git)
            push_state(github, output, previous)
        assert "store" in next(command for command in commands if command[:2] == ["git", "add"])

    monkeypatch.setattr(release_publish, "config", lambda: {
        **signing.settings, "integration_contract": "verified-origin-neutral-app-host",
    })
    monkeypatch.setattr(release_publish, "Signing", lambda *args: nullcontext(signing))
    monkeypatch.setattr(signing, "import_environment", lambda: None)
    monkeypatch.setattr(release_publish, "GitHub", lambda: SimpleNamespace(
        preflight=lambda: None, settings=signing.settings, repository=signing.settings["repository"],
    ))
    monkeypatch.setattr(release_publish, "run", no_git)
    monkeypatch.setattr(release_publish, "load_plan", lambda path: plan)
    monkeypatch.setattr(release_publish, "previous_snapshot", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(store, "prepare_release_snapshots", prepare)
    monkeypatch.setattr(store, "compose", store_index)
    monkeypatch.setattr(release_publish, "compose", apt_index)
    monkeypatch.setattr(release_publish, "release_assets", assets)
    monkeypatch.setattr(release_publish, "check_published_versions", lambda *args: None)
    monkeypatch.setattr(release_publish, "existing_release", lambda *args: None)
    monkeypatch.setattr(release_publish, "publish_release", lambda *args, **kwargs: events.append("release"))
    monkeypatch.setattr(release_publish, "push_snapshot", state)
    monkeypatch.setattr(release_publish.time, "sleep", lambda duration: None)
    monkeypatch.setattr(sys, "argv", [
        "release_publish.py", "publish", "--plan", str(tmp_path / "fixture-plan.json"),
        "--artifacts", str(tmp_path / "ci"), "--output", str(tmp_path / "publisher-apt"),
        "--cos", str(verifier.binary), "--cos-sha256", verifier.binary_sha256,
        "--publisher-key-id", verifier.publisher_key_id,
        "--app-signing-key", str(tmp_path / "package-key.json"), "--initialize",
    ])
    release_publish.main()
    assert events[:3] == ["authenticate", "store", "apt"]
    assert events[3:-1] == ["assets", "release"] * len(plan["selections"])
    assert events[-1] == "state"
