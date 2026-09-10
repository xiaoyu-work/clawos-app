import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from release_common import command_environment, config, control_bytes, run
from release_signing import Signing, primary_fingerprints


def pytest_addoption(parser):
    parser.addoption(
        "--provenance-cos-fixture",
        help="Explicit public cos CLI fixture for isolated snapshot signing; never a production tool pin",
    )
    parser.addoption("--provenance-cos-sha256", help="Expected digest of the explicit test-only CLI")
    parser.addoption("--native-settings-fixture", help="Explicit real Settings ELF for snapshot acceptance")
    parser.addoption("--native-notifications-fixture", help="Explicit real Notifications ELF for snapshot acceptance")
    parser.addoption(
        "--native-fixture-strip", action="store_true",
        help="Apply the release's standard strip step to private ELF copies, preserving loadable code/resources",
    )


def pytest_configure(config):
    if config.option.basetemp is None:
        config.option.basetemp = str(ROOT / "build/release-tests")
    scratch = ROOT / "build/release-python-work"
    scratch.mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(scratch)


@pytest.fixture
def native_mcp_probe():
    def probe(root, entry):
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "package-local-native-fixture", "version": "1"},
            }},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        arguments = [
            "bwrap", "--unshare-all", "--die-with-parent", "--clearenv",
            "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--ro-bind", root, "/app", "--chdir", "/app",
            "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/tmp",
            "--setenv", "COS_MCP_SERVER", "1", "--setenv", "COS_APP_MANIFEST", "/app/app.json",
            "--setenv", "XDG_CONFIG_HOME", "/tmp/config", "--setenv", "XDG_DATA_HOME", "/tmp/data",
            "/app/" + entry,
        ]
        result = subprocess.run(
            [str(value) for value in arguments], cwd=ROOT, env=command_environment(),
            input=b"".join(json.dumps(message).encode() + b"\n" for message in messages),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
        )
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        replies = {message["id"]: message for line in result.stdout.splitlines()
                   if "id" in (message := json.loads(line))}
        assert "error" not in replies[1] and "error" not in replies[2]
        return replies[2]["result"]["tools"]
    return probe


@pytest.fixture(scope="session")
def signing():
    root = ROOT / "build" / ("release-keys-" + uuid.uuid4().hex[:8])
    home = root / "generate"
    home.mkdir(parents=True, mode=0o700)
    phrase = b"release fixture passphrase"
    base = ["gpg", "--no-options", "--batch", "--homedir", home]
    try:
        run([*base, "--pinentry-mode", "loopback", "--passphrase-fd", "0",
             "--quick-generate-key", "Claw App Release Fixture", "ed25519", "sign", "1d"],
            input=phrase + b"\n")
        fingerprint = primary_fingerprints(run([*base, "--with-colons", "--list-keys"]).stdout)[0]
        public = root / "archive-key.asc"
        public.write_bytes(run([*base, "--armor", "--export", fingerprint]).stdout)
        private = run([*base, "--pinentry-mode", "loopback", "--passphrase-fd", "0",
                       "--armor", "--export-secret-keys", fingerprint], input=phrase + b"\n").stdout
        settings = {**config(), "signing_fingerprint": fingerprint,
                    "signing_key": public.relative_to(ROOT).as_posix()}
        with Signing(root / "sign", settings) as signer:
            signer.import_key(private, phrase)
            yield signer
    finally:
        run(["gpgconf", "--homedir", home, "--kill", "gpg-agent"], check=False)
        shutil.rmtree(root)


@pytest.fixture
def deb(tmp_path):
    counter = 0

    def make(name="claw-app-fixture", version="1.0.0", payload=b"first payload\n", *,
             architecture="all", extra=None, files=None, symlinks=None, control_files=None, modes=None):
        nonlocal counter
        counter += 1
        directory = tmp_path / f"deb-{counter}"
        root = directory / "stage"
        root.mkdir(parents=True)
        (root / "DEBIAN").mkdir()
        control = {
            "Package": name, "Version": version, "Architecture": architecture,
            "Maintainer": "Fixture <fixture@example.invalid>",
            "Description": "Harmless isolated App release fixture",
            **(extra or {}),
        }
        (root / "DEBIAN/control").write_bytes(control_bytes(control))
        for control_name, content in (control_files or {}).items():
            (root / "DEBIAN" / control_name).write_bytes(content)
        for relative, content in (files or {f"usr/share/clawos-fixture/{name}.txt": payload}).items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        for relative, destination in (symlinks or {}).items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(destination)
        for relative, mode in (modes or {}).items():
            (root / relative).chmod(mode)
        artifact = directory / f"{name}_{version}_{architecture}.deb"
        run(["dpkg-deb", "--root-owner-group", "--build", root, artifact],
            env={"SOURCE_DATE_EPOCH": "1700000000"})
        return artifact
    return make
