import io
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import struct
import sys
import tarfile

import pytest

from release_common import ROOT, digest, run, write_json
import release_snapshots as snapshots
import stage


@pytest.fixture
def runtime(request, tmp_path, monkeypatch):
    selected = request.config.getoption("--provenance-cos-fixture")
    if not selected:
        pytest.skip("Real signature checks require an explicit --provenance-cos-fixture")
    binary = Path(selected).resolve(strict=True)
    expected_digest = request.config.getoption("--provenance-cos-sha256")
    if expected_digest:
        assert digest(binary) == expected_digest, "Explicit provenance fixture digest changed"
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    (tmp_path / "passwd").write_text("root:x:0:0:fixture:/root:/bin/sh\n")
    (tmp_path / "group").write_text("root:x:0:\n")
    prefix = [
        "bwrap", "--unshare-all", "--uid", "0", "--gid", "0", "--die-with-parent", "--new-session",
        "--clearenv", "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/lib64", "/lib64", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--dir", "/etc", "--dir", "/tools", "--ro-bind", binary, "/tools/cos",
        "--bind", home, "/root", "--bind", tmp_path, tmp_path,
        "--ro-bind", tmp_path / "passwd", "/etc/passwd", "--ro-bind", tmp_path / "group", "/etc/group",
        "--setenv", "HOME", "/root", "--setenv", "PATH", "/usr/bin:/bin",
        "--setenv", "XDG_DATA_HOME", "/tmp/data", "--setenv", "XDG_CONFIG_HOME", "/tmp/config",
        "--chdir", tmp_path,
    ]

    def execute(arguments, **kwargs):
        assert Path(arguments[0]).resolve() == binary
        return run([*prefix, "/tools/cos", *arguments[1:]], **kwargs)

    def cli(*arguments):
        result = execute([binary, *arguments], check=False)
        assert result.returncode == 0, result.stdout.decode() + result.stderr.decode()
        value = json.loads(result.stdout)
        assert "error" not in value
        return value

    key_path = tmp_path / "package-key.json"
    key = cli("provenance", "keygen", "--out", key_path, "--comment", "isolated App snapshot fixture")
    write_json(tmp_path / "publisher.json", key["trust_entry"])
    cli("provenance", "trust", "add", "--file", tmp_path / "publisher.json")
    monkeypatch.setattr(snapshots, "run", execute)
    verifier = snapshots.Provenance(binary, digest(binary), key["key_id"])

    def sign(root, entries=("server.py",), resources=()):
        manifest = json.loads((root / "app.json").read_bytes())
        arguments = [
            "provenance", "sign", "--kind", "app", "--id", manifest["id"],
            "--version", manifest["version"], "--path", root, "--key", key_path,
        ]
        for entry in entries:
            arguments.extend(("--entrypoint", entry))
        for resource in resources:
            arguments.extend(("--resource", resource))
        result = cli(*arguments)
        assert result["signed"] is True
        return root

    try:
        yield verifier, sign
    finally:
        key_path.unlink()


@pytest.fixture
def app(tmp_path):
    counter = 0

    def make(app_id="snapshot-fixture", *, entry="server.py"):
        nonlocal counter
        counter += 1
        root = tmp_path / f"app-{counter}"
        root.mkdir(mode=0o755)
        manifest = json.loads((ROOT / "capabilities/storage-sdk/apps/kv/app.json").read_bytes())
        manifest["id"] = app_id
        manifest["mcp"]["entry"] = entry
        write_json(root / "app.json", manifest)
        (root / "server.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(tmp_path / 'entrypoint-executed')!r}).write_text('executed')\n"
            "raise RuntimeError('App entrypoints must never run during packaging or inspection')\n"
        )
        shutil.copy2(ROOT / "LICENSE", root / "LICENSE")
        return root

    return make


def build(root, output, runtime, signing, *, architecture="all"):
    verifier, _ = runtime
    return snapshots.build_catalog(
        root if isinstance(root, list) else [root], output, release_version="1.0.0",
        architecture=architecture, provenance=verifier, signing=signing,
    )


def resign_catalog(output, signing):
    catalog = snapshots.read_metadata(output / "catalog.json")
    (output / "SHA256SUMS").write_bytes(snapshots.checksum_bytes(output, catalog))
    signing.sign(output / "catalog.json", output / "catalog.json.asc", armored=True)
    signing.sign(output / "SHA256SUMS", output / "SHA256SUMS.asc", armored=True)


def test_signed_snapshot_is_complete_reproducible_and_never_executes_apps(tmp_path, runtime, signing, app):
    verifier, sign = runtime
    root = app()
    assets = root / "assets"
    assets.mkdir(mode=0o750)
    (assets / "empty").mkdir(mode=0o700)
    (assets / "config.json").write_text('{"retained":true}\n')
    (assets / "config.json").chmod(0o444)
    sign(root, resources=("assets/config.json",))
    original_manifest = (root / "app.json").read_bytes()
    original_envelope = (root / ".provenance.json").read_bytes()
    before = snapshots.tree_inventory(root, "all")
    first = build(root, tmp_path / "first", runtime, signing)
    second = build(root, tmp_path / "second", runtime, signing)
    assert first == second
    record = first["apps"][0]
    artifact = tmp_path / "first" / record["artifact"]["file"]
    assert artifact.read_bytes() == (tmp_path / "second" / record["artifact"]["file"]).read_bytes()
    extracted = tmp_path / "extracted"
    snapshots.extract_archive(artifact, extracted)
    assert snapshots.tree_inventory(extracted, "all") == before
    assert record["app_id"] == "snapshot-fixture"
    assert record["app_version"] == json.loads(original_manifest)["version"] != first["release_version"]
    assert record["manifest"] == {"path": "app.json", "size": len(original_manifest),
                                  "sha256": digest(root / "app.json")}
    assert (extracted / "app.json").read_bytes() == original_manifest
    assert (extracted / ".provenance.json").read_bytes() == original_envelope
    assert "permissions" not in record and "permission_review" not in record
    assert "permissions_granted" not in json.dumps(first)
    (root / "app.json").write_text('{"changed_after_packaging":true}')
    assert snapshots.verify_catalog(tmp_path / "first", verifier, signing) == first
    assert not (tmp_path / "entrypoint-executed").exists()


def test_cli_build_and_verify_use_existing_signing_contracts(
    tmp_path, runtime, signing, app, monkeypatch, capsys,
):
    verifier, sign = runtime
    root = sign(app())
    output = tmp_path / "output"
    private = run(signing.gpg(
        "--pinentry-mode", "loopback", "--passphrase-fd", "0",
        "--armor", "--export-secret-keys", signing.fingerprint,
    ), input=signing.passphrase + b"\n").stdout
    monkeypatch.setenv("CLAW_APPS_APT_SIGNING_PRIVATE_KEY", private.decode())
    monkeypatch.setenv("CLAW_APPS_APT_SIGNING_PASSPHRASE", signing.passphrase.decode())
    monkeypatch.setattr(snapshots, "Signing", lambda workspace: type(signing)(workspace, signing.settings))
    arguments = [
        "release_snapshots.py", "build", "--app-directory", str(root), "--release-version", "1.0.0",
        "--output", str(output), "--cos", str(verifier.binary), "--cos-sha256", verifier.binary_sha256,
        "--publisher-key-id", verifier.publisher_key_id,
    ]
    monkeypatch.setattr(sys, "argv", arguments)
    snapshots.main()
    built = json.loads(capsys.readouterr().out)
    assert "CLAW_APPS_APT_SIGNING_PRIVATE_KEY" not in os.environ
    assert "CLAW_APPS_APT_SIGNING_PASSPHRASE" not in os.environ
    monkeypatch.setattr(sys, "argv", [
        "release_snapshots.py", "verify", "--output", str(output),
        "--cos", str(verifier.binary), "--cos-sha256", verifier.binary_sha256,
        "--publisher-key-id", verifier.publisher_key_id,
    ])
    snapshots.main()
    assert json.loads(capsys.readouterr().out) == built
    shutil.copy2(signing.public_key, tmp_path / "archive-key.asc")
    write_json(tmp_path / "fixture.json", {
        "test_only": True, "catalog": str(output / "catalog.json"),
        "public_archive_key": str(tmp_path / "archive-key.asc"),
        "archive_fingerprint": signing.fingerprint, "public_app_publisher": str(tmp_path / "publisher.json"),
        "publisher_key_id": verifier.publisher_key_id, "cli": str(verifier.binary),
        "cli_sha256": verifier.binary_sha256, "installed": False, "permissions_granted": False,
    })
    assert not (tmp_path / "entrypoint-executed").exists()


@pytest.mark.parametrize("mutation", ["manifest", "signature", "unsigned"])
def test_unsigned_or_changed_package_never_creates_catalog(tmp_path, runtime, signing, app, mutation):
    _, sign = runtime
    root = app()
    if mutation != "unsigned":
        sign(root)
        if mutation == "manifest":
            with (root / "app.json").open("ab") as stream:
                stream.write(b"\n")
        else:
            envelope = snapshots.read_metadata(root / ".provenance.json")
            envelope["signature"]["value"] = "00" * 64
            write_json(root / ".provenance.json", envelope)
    with pytest.raises(ValueError, match="Unsigned App|provenance verification failed"):
        build(root, tmp_path / "output", runtime, signing)
    assert not (tmp_path / "output").exists()
    assert not (tmp_path / "entrypoint-executed").exists()


def test_pinned_publisher_is_required_in_addition_to_active_trust(tmp_path, runtime, signing, app):
    verifier, sign = runtime
    root = sign(app())
    wrong = snapshots.Provenance(verifier.binary, verifier.binary_sha256, "sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="pinned package-signing publisher"):
        build(root, tmp_path / "output", (wrong, sign), signing)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("field", ["manifest", "provenance", "app_id", "app_version"])
def test_signed_catalog_cannot_substitute_authenticated_manifest_data(tmp_path, runtime, signing, app, field):
    verifier, sign = runtime
    output = tmp_path / "output"
    catalog = build(sign(app()), output, runtime, signing)
    record = catalog["apps"][0]
    if field in ("manifest", "provenance"):
        record[field]["sha256"] = "0" * 64
    else:
        record[field] = "substituted"
    write_json(output / "catalog.json", catalog)
    resign_catalog(output, signing)
    with pytest.raises(ValueError, match="does not bind the authenticated manifest"):
        snapshots.verify_catalog(output, verifier, signing)


def test_catalog_signature_is_required_before_untrusted_artifact_names(tmp_path, runtime, signing, app):
    verifier, sign = runtime
    output = tmp_path / "output"
    catalog = build(sign(app()), output, runtime, signing)
    catalog["apps"][0]["artifact"]["file"] = "../../untrusted.tar.gz"
    write_json(output / "catalog.json", catalog)
    with pytest.raises(subprocess.CalledProcessError) as error:
        snapshots.verify_catalog(output, verifier, signing)
    assert "gpgv" in str(error.value)


def test_apt_signature_cannot_authorize_changed_app_bytes(tmp_path, runtime, signing, app):
    verifier, sign = runtime
    output = tmp_path / "output"
    catalog = build(sign(app()), output, runtime, signing)
    record = catalog["apps"][0]
    old_archive = output / record["artifact"]["file"]
    root = tmp_path / "tampered"
    snapshots.extract_archive(old_archive, root)
    with (root / "app.json").open("ab") as stream:
        stream.write(b"\n")
    candidate = tmp_path / "tampered.tar.gz"
    snapshots.write_archive(root, snapshots.tree_inventory(root, "all"), candidate)
    checksum = digest(candidate)
    filename = f"claw-app-snapshot-{checksum}.tar.gz"
    candidate.rename(output / filename)
    old_archive.unlink()
    record["artifact"].update(file=filename, sha256=checksum, size=(output / filename).stat().st_size)
    write_json(output / "catalog.json", catalog)
    resign_catalog(output, signing)
    with pytest.raises(ValueError, match="provenance verification failed"):
        snapshots.verify_catalog(output, verifier, signing)


def test_catalog_verification_reads_its_private_snapshot_after_authentication(
    tmp_path, runtime, signing, app, monkeypatch,
):
    verifier, sign = runtime
    output = tmp_path / "output"
    catalog = build(sign(app()), output, runtime, signing)
    verify = signing.verify
    replaced = False

    def replace_source(signature, source):
        nonlocal replaced
        verify(signature, source)
        if source.name == "catalog.json" and not replaced:
            replaced = True
            assert source.parent != output
            write_json(output / "catalog.json", {"unsigned": "changed after signature verification"})

    monkeypatch.setattr(signing, "verify", replace_source)
    assert snapshots.verify_catalog(output, verifier, signing) == catalog
    assert replaced
    assert snapshots.read_metadata(output / "catalog.json") == {
        "unsigned": "changed after signature verification",
    }


@pytest.mark.parametrize("app_id", ["cosmic-settings", "pkg", "arbitrary-app"])
def test_absolute_mcp_entry_has_no_product_or_language_exemption(tmp_path, runtime, signing, app, app_id):
    _, sign = runtime
    root = sign(app(app_id, entry="/usr/bin/outside-snapshot"))
    with pytest.raises(ValueError, match="Unsafe App-relative path"):
        build(root, tmp_path / "output", runtime, signing)


def test_manifest_entry_must_be_a_declared_signed_entrypoint(tmp_path, runtime, signing, app):
    _, sign = runtime
    root = app(entry="other.py")
    (root / "other.py").write_text("raise RuntimeError('never execute')\n")
    sign(root)
    with pytest.raises(ValueError, match="not a declared signed package-local entrypoint"):
        build(root, tmp_path / "output", runtime, signing)


@pytest.mark.parametrize("language,main,server", [
    ("python", "main.py", "server.py"), ("node", "main.js", "server.js"),
    ("shell", "main.sh", "server.sh"), ("binary", "main", "server"),
])
def test_public_runtime_defaults_cover_each_declared_surface(language, main, server):
    assert snapshots.manifest_entries({"runtime": language}) == [("operation/GUI", main)]
    assert snapshots.manifest_entries({"runtime": language, "mcp": {}}) == [("MCP/background", server)]
    assert snapshots.manifest_entries({
        "runtime": language, "desktop": {"exec": "--gui"}, "mcp": {"lifecycle": "always-on"},
    }) == [("operation/GUI", main), ("MCP/background", server)]
    assert snapshots.manifest_entries({
        "runtime": language, "entry": "bin/application", "mcp": {"entry": "bin/service"},
    }) == [("operation/GUI", "bin/application"), ("MCP/background", "bin/service")]


@pytest.mark.parametrize("language,server", [
    ("python", "server.py"), ("node", "server.js"), ("shell", "server.sh"), ("binary", "server"),
])
def test_mcp_only_snapshots_honor_default_entry_without_inventing_main(
    tmp_path, runtime, signing, app, language, server,
):
    _, sign = runtime
    root = app()
    manifest = snapshots.read_metadata(root / "app.json")
    manifest["runtime"] = language
    manifest["mcp"].pop("entry")
    manifest["mcp"]["lifecycle"] = "always-on"
    write_json(root / "app.json", manifest)
    architecture = "all"
    if language == "binary":
        shutil.copy2("/usr/bin/true", root / server)
        architecture = {"x86_64": "amd64", "aarch64": "arm64"}[platform.machine()]
    elif language == "node":
        (root / server).write_text("throw new Error('must not execute');\n")
    elif language == "shell":
        (root / server).write_text("#!/bin/sh\nexit 97\n")
    sign(root, entries=(server,))
    catalog = build(root, tmp_path / "output", runtime, signing, architecture=architecture)
    extracted = tmp_path / "extracted"
    snapshots.extract_archive(tmp_path / "output" / catalog["apps"][0]["artifact"]["file"], extracted)
    assert (extracted / "app.json").read_bytes() == (root / "app.json").read_bytes()
    assert not any((extracted / name).exists() for name, _ in snapshots.RUNTIME_ENTRIES.values())
    assert not (tmp_path / "entrypoint-executed").exists()


@pytest.mark.parametrize("surface", ["operations", "desktop"])
def test_operation_and_gui_entries_need_the_same_signed_binding(
    tmp_path, runtime, signing, app, surface,
):
    _, sign = runtime
    root = app()
    manifest = snapshots.read_metadata(root / "app.json")
    manifest[surface] = {"show": {"label": {"en": "Show"}}} if surface == "operations" else {"exec": "--gui"}
    write_json(root / "app.json", manifest)
    shutil.copy2(root / "server.py", root / "main.py")
    sign(root)
    with pytest.raises(ValueError, match="operation/GUI entry is not a declared signed"):
        build(root, tmp_path / "rejected", runtime, signing)
    sign(root, entries=("main.py", "server.py"))
    build(root, tmp_path / "accepted", runtime, signing)
    assert not (tmp_path / "rejected").exists()
    assert not (tmp_path / "entrypoint-executed").exists()


@pytest.mark.parametrize("app_id", ["mail-ai", "cosmic-settings", "unrelated-app"])
def test_main_entry_has_no_identity_or_origin_exemption(tmp_path, runtime, signing, app, app_id):
    _, sign = runtime
    root = app(app_id)
    manifest = snapshots.read_metadata(root / "app.json")
    manifest["entry"] = "/usr/bin/outside-snapshot"
    manifest["desktop"] = {"exec": "--gui"}
    write_json(root / "app.json", manifest)
    sign(root)
    with pytest.raises(ValueError, match="Unsafe App-relative path"):
        build(root, tmp_path / "output", runtime, signing)


@pytest.mark.parametrize("manifest", [
    {"runtime": "privileged"}, {"operations": []}, {"desktop": False},
    {"mcp": None}, {"mcp": {"lifecycle": "root-service"}}, {"entry": None},
])
def test_invalid_surface_metadata_fails_explicitly(manifest):
    with pytest.raises(ValueError):
        snapshots.manifest_entries(manifest)


def test_binary_entry_requires_executable_mode_without_running_it(app):
    root = app()
    manifest = snapshots.read_metadata(root / "app.json")
    manifest["runtime"] = "binary"
    (root / "server.py").chmod(0o644)
    with pytest.raises(ValueError, match="binary entry must be executable"):
        snapshots.validate_manifest_entries(root, manifest, ["server.py"])


@pytest.mark.parametrize("field,claim", [
    ("contract_digest", "sha256:" + "0" * 64),
    ("permission_review", {"approved": True, "permissions_granted": True, "presenter": "app"}),
    ("permission_choices", [{"verb": "fs.read", "decision": "allow", "scope": {"kind": "wild"}}]),
    ("first_review", {"yes": True, "printed_json": True}),
])
@pytest.mark.parametrize("location", ["catalog", "app"])
def test_signed_catalog_claims_cannot_stand_in_for_os_review(
    tmp_path, runtime, signing, app, field, claim, location,
):
    verifier, sign = runtime
    output = tmp_path / "output"
    catalog = build(sign(app()), output, runtime, signing)
    target = catalog if location == "catalog" else catalog["apps"][0]
    target[field] = claim
    write_json(output / "catalog.json", catalog)
    resign_catalog(output, signing)
    with pytest.raises(ValueError, match="Unsupported App snapshot catalog|Invalid App catalog record"):
        snapshots.verify_catalog(output, verifier, signing)


@pytest.mark.parametrize("change", ["scope", "why", "lifecycle"])
def test_requested_scopes_purposes_and_surfaces_remain_authenticated_data(
    tmp_path, runtime, signing, app, change,
):
    _, sign = runtime
    root = app("review-neutral")
    manifest = snapshots.read_metadata(root / "app.json")
    need = {
        "verb": "fs.read", "scope": {"kind": "from-arg", "arg": "path"},
        "when": {"kind": "arg-present", "arg": "path"},
        "why": {"en": "Read the chosen input file.", "fr": "Lire le fichier choisi."},
    }
    manifest["operations"] = {"open": {
        "label": {"en": "Open"},
        "args": [{"name": "path", "kind": "path", "binding": "positional", "required": True}],
        "needs": [need],
    }}
    manifest["desktop"] = {"exec": "--gui", "name": {"en": "Review-neutral UI"}}
    manifest["mcp"]["lifecycle"] = "always-on"
    write_json(root / "app.json", manifest)
    shutil.copy2(root / "server.py", root / "main.py")
    sign(root, entries=("main.py", "server.py"))
    original = (root / "app.json").read_bytes()
    first = build(root, tmp_path / "first", runtime, signing)
    if change == "scope":
        need["scope"] = {"kind": "wild"}
    elif change == "why":
        need["why"]["en"] = "Read the input file for the requested report."
    else:
        manifest["mcp"]["lifecycle"] = "while-app-running"
    write_json(root / "app.json", manifest)
    sign(root, entries=("main.py", "server.py"))
    updated = (root / "app.json").read_bytes()
    second = build(root, tmp_path / "second", runtime, signing)
    before, after = first["apps"][0], second["apps"][0]
    assert before["app_id"] == after["app_id"] == "review-neutral"
    assert before["app_version"] == after["app_version"]
    assert before["manifest"]["sha256"] != after["manifest"]["sha256"]
    assert before["artifact"]["sha256"] != after["artifact"]["sha256"]
    for name, catalog, expected in (("first", first, original), ("second", second, updated)):
        record = catalog["apps"][0]
        extracted = tmp_path / f"{name}-extracted"
        snapshots.extract_archive(tmp_path / name / record["artifact"]["file"], extracted)
        assert (extracted / "app.json").read_bytes() == expected
        requests = snapshots.read_metadata(extracted / "app.json")
        assert requests["operations"]["open"]["needs"][0]["why"]["fr"] == "Lire le fichier choisi."
        assert requests["mcp"]["tools"][0]["needs"][0]["why"]
        assert "purpose" not in requests and "plugin" not in requests
        assert set(record) == {"app_id", "app_version", "architecture", "artifact", "manifest", "provenance"}
        assert not {"contract_digest", "permission_review", "permissions_granted", "permission_choices"} & set(record)
    assert not (tmp_path / "entrypoint-executed").exists()


def test_selected_apps_stay_separate_and_existing_output_is_immutable(tmp_path, runtime, signing, app):
    _, sign = runtime
    one, two = sign(app("first-app")), sign(app("second-app"))
    output = tmp_path / "output"
    catalog = build([two, one], output, runtime, signing)
    assert [record["app_id"] for record in catalog["apps"]] == ["first-app", "second-app"]
    before = (output / "catalog.json").read_bytes()
    with pytest.raises(ValueError, match="immutable output"):
        build(one, output, runtime, signing)
    assert (output / "catalog.json").read_bytes() == before
    with pytest.raises(ValueError, match="separate and unique"):
        build([one, one], tmp_path / "duplicate", runtime, signing)
    assert not (tmp_path / "duplicate").exists()


def test_complete_browser_and_mail_resources_remain_inside_signed_snapshots(tmp_path, runtime, signing):
    _, sign = runtime
    roots, expected = [], {}
    for product, app_id in (("browser", "browser-attached"), ("mail", "mail-ai")):
        staged = tmp_path / f"{product}-stage"
        stage.stage(product, staged, [app_id])
        root = tmp_path / f"{product}-snapshot"
        shutil.copytree(staged / "usr/lib/cos/apps" / app_id, root, symlinks=True)
        resources = root / "assets"
        resources.mkdir()
        if product == "browser":
            shutil.copytree(staged / "usr/share/claw/extensions/claw-agent-browser", resources / "extension")
        else:
            shutil.copy2(staged / "usr/lib/thunderbird/distribution/extensions/claw-mail-ai@claw.os.xpi",
                         resources / "claw-mail-ai@claw.os.xpi")
        entries = tuple(sorted({
            entry for _, entry in snapshots.manifest_entries(snapshots.read_metadata(root / "app.json"))
        }))
        sign(root, entries=entries)
        expected[app_id] = snapshots.tree_inventory(root, "all")
        roots.append(root)
    catalog = build(roots, tmp_path / "output", runtime, signing)
    for record in catalog["apps"]:
        extracted = tmp_path / f"extracted-{record['app_id']}"
        snapshots.extract_archive(tmp_path / "output" / record["artifact"]["file"], extracted)
        assert snapshots.tree_inventory(extracted, "all") == expected[record["app_id"]]
    browser = tmp_path / "extracted-browser-attached"
    assert (browser / "native_host.py").is_file()
    assert {path.name for path in (browser / "assets/extension").iterdir()} >= {
        "manifest.json", "background.js", "content.js", "popup.html", "popup.js", "README.md",
    }
    assert (tmp_path / "extracted-mail-ai/assets/claw-mail-ai@claw.os.xpi").is_file()
    shutil.copy2(signing.public_key, tmp_path / "archive-key.asc")


def native_loaded_image(path):
    with path.open("rb") as stream:
        header = struct.unpack("<16sHHIQQQIHHHHHH", stream.read(64))
        stream.seek(header[5])
        segments = [
            struct.unpack("<IIQQQQQQ", stream.read(header[9]))
            for _ in range(header[10])
        ]
        loaded = []
        for segment in segments:
            if segment[0] != 1:
                continue
            offset, size = segment[2], segment[5]
            # Stripping changes the ELF section-table metadata, not its loaded program.
            skipped = 64 if offset == 0 else 0
            stream.seek(offset + skipped)
            loaded.append((segment, hashlib.sha256(stream.read(size - skipped)).hexdigest()))
    return header[:6], header[7:11], loaded


@pytest.mark.parametrize("product,option", [
    ("settings", "--native-settings-fixture"),
    ("notifications", "--native-notifications-fixture"),
])
def test_real_native_package_local_signed_acceptance(
    product, option, request, tmp_path, runtime, signing, native_mcp_probe,
):
    import native_payload

    supplied = request.config.getoption(option)
    if not supplied:
        pytest.skip(f"Real native acceptance requires the explicit {option} ELF")
    binary = Path(supplied).resolve(strict=True)
    selected = native_payload.plan(product)
    architecture = {"x86_64": "amd64", "aarch64": "arm64"}[platform.machine()]
    installed = tmp_path / "installer"
    native = installed / "usr/bin" / selected.program
    native.parent.mkdir(parents=True)
    shutil.copy2(binary, native)
    original_digest = digest(binary)
    stripped = request.config.getoption("--native-fixture-strip")
    if stripped:
        loaded = native_loaded_image(native)
        run(["strip", "--strip-unneeded", native])
        assert native_loaded_image(native) == loaded
    source_digest = digest(native)
    resource_scope = "The original Notifications installer ships only its real ELF."
    if product == "settings":
        resources = ROOT / "products/settings/native/cosmic-settings/resources"
        for origin, target in (
            ("icons", "usr/share/icons/hicolor"),
            ("default_schema", "usr/share/cosmic"),
            ("applications", "usr/share/applications"),
        ):
            shutil.copytree(resources / origin, installed / target)
        target = installed / "usr/share/metainfo/com.clawos.Settings.metainfo.xml"
        target.parent.mkdir(parents=True)
        shutil.copy2(resources / target.name, target)
        resource_scope = (
            "Real ELF and original icon/schema/application/metainfo source bytes. "
            "This archive-only fixture does not supply Settings' forbidden polkit outputs; "
            "the complete installer is separately tested to fail rather than strip them."
        )
    prepared = native_payload.prepare(selected, installed, tmp_path / "native-app", architecture)
    manifest_bytes = (selected.source / "app.json").read_bytes()
    verifier, sign = runtime
    sign(prepared.root, entries=prepared.entrypoints, resources=prepared.resources)
    envelope = snapshots.read_metadata(prepared.root / ".provenance.json")
    assert envelope["package"]["entrypoints"] == list(prepared.entrypoints)
    signed_entry, = [
        item for item in envelope["package"]["files"]
        if item.get("path") == prepared.entrypoints[0]
    ]
    assert signed_entry["type"] == "file"
    assert signed_entry["digest"] == "sha256:" + source_digest
    assert signed_entry["size"] == native.stat().st_size
    assert digest(binary) == original_digest
    catalog = build(prepared.root, tmp_path / "catalog", runtime, signing, architecture=architecture)
    assert snapshots.verify_catalog(tmp_path / "catalog", verifier, signing) == catalog
    extracted = tmp_path / "extracted"
    snapshots.extract_archive(tmp_path / "catalog" / catalog["apps"][0]["artifact"]["file"], extracted)
    assert (extracted / "app.json").read_bytes() == manifest_bytes
    assert digest(extracted / prepared.entrypoints[0]) == source_digest
    assert (extracted / prepared.entrypoints[0]).stat().st_mode & 0o777 == native.stat().st_mode & 0o777
    assert (extracted / prepared.entrypoints[0]).stat().st_nlink == 1
    for resource in prepared.resources:
        assert (extracted / resource).read_bytes() == (installed / resource.removeprefix("resources/")).read_bytes()
    tools = native_mcp_probe(extracted, prepared.entrypoints[0])
    manifest = json.loads(manifest_bytes)
    assert {tool["name"] for tool in tools} == {
        tool["name"] for tool in manifest["mcp"]["tools"]
    }
    write_json(tmp_path / "native-acceptance.json", {
        "product": product, "binary_fixture": str(binary), "original_fixture_sha256": original_digest,
        "original_fixture_size": binary.stat().st_size, "standard_release_strip": stripped,
        "binary_sha256": source_digest, "binary_size": native.stat().st_size,
        "loaded_code_and_resources_preserved": True,
        "entrypoints": list(prepared.entrypoints),
        "resource_files": len(prepared.resources), "resource_scope": resource_scope,
        "manifest_sha256": digest(extracted / "app.json"), "catalog_record": catalog["apps"][0],
        "real_elf": True, "isolated_mcp_tools_list": True, "live_desktop_or_provider_used": False,
        "runtime_resource_or_gui_acceptance": False, "publication": False,
    })


def test_real_panel_elf_and_original_resources_are_preserved(tmp_path, runtime, signing, app):
    _, sign = runtime
    installed = ROOT / "build/native-boundary-install/calendar"
    binary = installed / "usr/bin/claw-applet-calendar"
    if not binary.is_file():
        pytest.skip("Explicit candidate panel installer output is unavailable; this is not a native build substitute")
    root = app()
    (root / "bin").mkdir()
    shutil.copy2(binary, root / "bin/claw-applet-calendar")
    shutil.copytree(installed / "usr/share", root / "assets")
    sign(root, entries=("server.py", "bin/claw-applet-calendar"))
    original = snapshots.tree_inventory(root, "amd64")
    catalog = build(root, tmp_path / "output", runtime, signing, architecture="amd64")
    archive = tmp_path / "output" / catalog["apps"][0]["artifact"]["file"]
    extracted = tmp_path / "extracted"
    snapshots.extract_archive(archive, extracted)
    assert snapshots.tree_inventory(extracted, "amd64") == original
    assert (extracted / "bin/claw-applet-calendar").stat().st_mode & 0o777 == 0o755
    assert digest(extracted / "bin/claw-applet-calendar") == digest(binary)
    assert (extracted / "assets/applications/com.clawos.PanelCalendarButton.desktop").is_file()
    assert (extracted / "assets/icons/hicolor/scalable/actions/com.clawos.PanelCalendarButton-symbolic.svg").is_file()


@pytest.mark.parametrize("name", ["DEBIAN/postinst", "postinst", "../escape", "/absolute", "bad\\path", ".", "a/../b"])
def test_generic_snapshot_paths_cannot_be_root_hooks_or_escape(name):
    with pytest.raises(ValueError, match="root hooks|Unsafe App-relative path"):
        snapshots.app_path(name)


@pytest.mark.parametrize("mode", [0o666, 0o4755, 0o2755])
def test_privilege_or_shared_writable_modes_are_refused(app, mode):
    root = app()
    (root / "server.py").chmod(mode)
    with pytest.raises(ValueError, match="Unsafe App payload mode"):
        snapshots.tree_inventory(root, "all")


@pytest.mark.parametrize("case", ["escape", "fifo", "case-collision", "xattr"])
def test_unsafe_source_nodes_are_refused(app, case):
    root = app()
    if case == "escape":
        (root / "link").symlink_to("../")
    elif case == "fifo":
        os.mkfifo(root / "fifo")
    elif case == "case-collision":
        (root / "SERVER.py").write_text("not the same file")
    else:
        os.setxattr(root / "server.py", "user.unbound-metadata", b"not signed by provenance")
    with pytest.raises(ValueError, match="symlinks|special file|case-colliding|extended attributes"):
        snapshots.tree_inventory(root, "all")


def test_real_elf_cannot_be_labeled_architecture_independent(app):
    root = app()
    shutil.copy2("/usr/bin/true", root / "binary-fixture")
    with pytest.raises(ValueError, match="ELF payload does not match snapshot architecture all"):
        snapshots.tree_inventory(root, "all")


def test_wrong_tool_pin_fails_before_running_any_command(tmp_path, monkeypatch):
    binary = tmp_path / "cos"
    binary.write_text("#!/bin/sh\nexit 99\n")
    binary.chmod(0o755)
    monkeypatch.setattr(snapshots, "run", lambda *_a, **_k: pytest.fail("unverified tool must not execute"))
    with pytest.raises(ValueError, match="executable SHA256 pin"):
        snapshots.Provenance(binary, "0" * 64, "sha256:" + "0" * 64)


@pytest.mark.parametrize("content", ['{"id":"first","id":"second"}', '{"value":NaN}', '{"value":Infinity}'])
def test_ambiguous_or_non_json_metadata_is_rejected(tmp_path, content):
    path = tmp_path / "metadata.json"
    path.write_text(content)
    with pytest.raises(ValueError, match="Duplicate JSON|Non-finite JSON"):
        snapshots.read_metadata(path)


def test_metadata_size_limit_is_checked_before_parsing(tmp_path, monkeypatch):
    path = tmp_path / "metadata.json"
    path.write_bytes(b'{"id":"fixture"}')
    monkeypatch.setattr(snapshots, "MAX_METADATA", path.stat().st_size)
    assert snapshots.read_metadata(path) == {"id": "fixture"}
    with path.open("ab") as stream:
        stream.write(b"\n")
    with pytest.raises(ValueError, match="bounded regular metadata"):
        snapshots.read_metadata(path)


def test_long_utf8_pax_paths_preserve_the_complete_file(tmp_path, app):
    root = app()
    resource = root / ("a" * 100) / ("b" * 100) / ("c" * 100 + "\N{SNOWMAN}")
    resource.parent.mkdir(parents=True)
    resource.write_bytes(b"complete resource\n")
    inventory = snapshots.tree_inventory(root, "all")
    archive = tmp_path / "long-path.tar.gz"
    snapshots.write_archive(root, inventory, archive)
    snapshots.extract_archive(archive, tmp_path / "extracted")
    assert snapshots.tree_inventory(tmp_path / "extracted", "all") == inventory


@pytest.mark.parametrize("case", ["oversized-pax", "nested-pax", "truncated-member", "trailing-data"])
def test_tar_metadata_limits_apply_before_extended_header_parsing(tmp_path, monkeypatch, case):
    monkeypatch.setattr(snapshots, "MAX_METADATA", 32)
    member = tarfile.TarInfo("header")
    if case in ("oversized-pax", "nested-pax"):
        member.type = tarfile.XHDTYPE
        member.size = 33 if case == "oversized-pax" else 0
        content = member.tobuf(format=tarfile.USTAR_FORMAT)
        if case == "nested-pax":
            content += content
    elif case == "truncated-member":
        member.size = 1024
        content = member.tobuf(format=tarfile.USTAR_FORMAT) + b"short"
    else:
        content = member.tobuf(format=tarfile.USTAR_FORMAT) + b"\0" * 1024 + b"unindexed"
    archive = tmp_path / "invalid-metadata.tar.gz"
    archive.write_bytes(gzip.compress(content))
    with pytest.raises(ValueError, match="metadata|truncated|trailing"):
        snapshots.extract_archive(archive, tmp_path / "extracted")
    assert not (tmp_path / "extracted").exists()


def test_public_provenance_does_not_sign_or_silently_dereference_symlinks(runtime, app):
    _, sign = runtime
    root = app()
    (root / "linked-entry.py").symlink_to("server.py")
    with pytest.raises(ValueError, match="cannot sign symlinks"):
        snapshots.tree_inventory(root, "all")
    with pytest.raises(AssertionError, match="symlinks cannot be signed"):
        sign(root)
    assert not (root / ".provenance.json").exists()


@pytest.mark.parametrize("case", ["escape", "root-hook", "hardlink", "setuid", "symlink-parent"])
def test_unsafe_archives_fail_without_writing_outside_snapshot(tmp_path, case):
    archive_path = tmp_path / "malicious.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo("../escape" if case == "escape" else "postinst" if case == "root-hook" else "file")
        member.mode = 0o4755 if case == "setuid" else 0o644
        if case == "hardlink":
            member.type = tarfile.LNKTYPE
            member.linkname = "app.json"
            archive.addfile(member)
        elif case == "symlink-parent":
            member.type = tarfile.SYMTYPE
            member.linkname = "."
            archive.addfile(member)
            child = tarfile.TarInfo("file/child")
            child.size = 1
            archive.addfile(child, io.BytesIO(b"x"))
        else:
            member.size = 1
            archive.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(ValueError):
        snapshots.extract_archive(archive_path, tmp_path / "extracted")
    assert not (tmp_path / "escape").exists()
