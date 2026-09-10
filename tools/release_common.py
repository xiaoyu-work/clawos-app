"""Shared, fail-closed contracts for independently released App packages."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SECRET_ENV = {
    "CLAW_APPS_APT_SIGNING_PRIVATE_KEY", "CLAW_APPS_APT_SIGNING_PASSPHRASE",
}


def command_environment(extra=None):
    environment = {**os.environ, **(extra or {})}
    return {key: value for key, value in environment.items() if key not in SECRET_ENV}


def run(arguments, *, cwd=ROOT, input=None, env=None, check=True):
    return subprocess.run(
        [str(argument) for argument in arguments], cwd=cwd, input=input,
        env=command_environment(env), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check,
    )


def config():
    value = json.loads((ROOT / "packaging/release.json").read_text())
    if value.get("format") != "claw.app-release/v1":
        raise ValueError("Unsupported App release configuration")
    if value["architectures"] != ["amd64", "arm64"]:
        raise ValueError("The native release contract requires amd64 and arm64")
    if not re.fullmatch(r"[0-9A-F]{40}", value["signing_fingerprint"]):
        raise ValueError("Missing checked-in archive signing fingerprint")
    if not 1 <= value["validity_days"] <= 14:
        raise ValueError("APT validity must be bounded to at most fourteen days")
    run(["dpkg", "--validate-version", value["migration_before"]])
    return value


def version(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
        r"(?:~(?:alpha|beta|rc)[1-9][0-9]*)?(?:-[1-9][0-9]*)?", value,
    ) or len(value) > 80:
        raise ValueError("Version must be MAJOR.MINOR.PATCH[~alphaN|~betaN|~rcN][-REVISION]")
    run(["dpkg", "--validate-version", value])
    return value


def compare_versions(left, operation, right):
    result = run(["dpkg", "--compare-versions", left, operation, right], check=False)
    if result.returncode not in (0, 1):
        raise ValueError("Invalid Debian version comparison")
    return result.returncode == 0


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def digest(path, algorithm="sha256"):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def relative_path(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_+./~@-]+", value):
        raise ValueError("Invalid archive-relative path")
    path = Path(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError("Archive path escapes its root")
    return path


def work_path(path):
    path = path.resolve()
    build = (ROOT / "build").resolve()
    if path == build or not path.is_relative_to(build):
        raise ValueError("Release output and fixture roots must be explicit directories under build/")
    return path


def license_files(root):
    paths = root.rglob("*") if root.is_dir() else [root]
    return sorted(path for path in paths if path.is_file() and re.fullmatch(
        r"(?:LICENSE|COPYING|COPYRIGHT|NOTICE)(?:[._-].*)?", path.name, re.IGNORECASE,
    ))


def fields(text):
    result = {}
    current = None
    for line in text.splitlines():
        if not line:
            raise ValueError("Unexpected empty Debian control stanza")
        if line.startswith((" ", "\t")):
            if current is None:
                raise ValueError("Unbound Debian continuation line")
            result[current] += "\n" + line
        else:
            name, separator, value = line.partition(":")
            if not separator or name in result or not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", name):
                raise ValueError("Invalid or duplicate Debian control field")
            result[name] = value.lstrip()
            current = name
    return result


def control_bytes(value):
    for name, content in value.items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", name) or not isinstance(content, str):
            raise ValueError("Invalid Debian control field")
        if "\r" in content or any(not line.startswith(" ") for line in content.split("\n")[1:]):
            raise ValueError("Invalid Debian control continuation")
    return "".join(
        f"{name}:{'' if not content or content.startswith(chr(10)) else ' '}{content}\n"
        for name, content in value.items()
    ).encode()


def package_record(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Release package must be a regular .deb file")
    control = fields(run(["dpkg-deb", "--field", path]).stdout.decode().strip())
    name, release, architecture = (control[key] for key in ("Package", "Version", "Architecture"))
    if not re.fullmatch(r"claw-(?:app|cap|apps)-[a-z0-9][a-z0-9-]*", name):
        raise ValueError("Not an App-owned Debian package")
    version(release)
    if architecture not in ("all", "amd64", "arm64"):
        raise ValueError("Unsupported package architecture")
    filename = f"{name}_{release}_{architecture}.deb"
    if path.name != filename:
        raise ValueError("Package filename does not match its control metadata")
    from release_payload import validate_deb

    validate_deb(path, environment=command_environment(), scratch=ROOT / "build")
    return {
        "package": name, "version": release, "architecture": architecture,
        "filename": f"pool/main/{name}/{filename}", "size": path.stat().st_size,
        "sha256": digest(path), "sha512": digest(path, "sha512"), "control": control,
    }


def identity(record):
    return record["package"], record["version"], record["architecture"]
