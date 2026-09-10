"""Stage explicitly pinned pure-Python dependencies missing from Debian trixie."""

import fcntl
import hashlib
import io
from pathlib import Path
import re
import shutil
import stat
import urllib.parse
import urllib.request
import zipfile

from release_common import ROOT, config, digest, relative_path


def wheel_path(specification):
    location = urllib.parse.urlsplit(specification["url"])
    filename = Path(location.path).name
    expected = f"{specification['distribution'].replace('-', '_')}-{specification['version']}-py3-none-any.whl"
    if location.scheme != "https" or location.netloc != "files.pythonhosted.org" or (
        location.query or location.fragment or filename != expected
    ) or not re.fullmatch(r"[0-9a-f]{64}", specification["sha256"]) or not (
        isinstance(specification["size"], int) and 0 < specification["size"] <= 10_000_000
    ):
        raise ValueError("Python dependency must be an exact size/digest-pinned pure wheel")
    path = ROOT / "build/release-wheels" / specification["sha256"] / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.parent / "download.lock").open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if not path.exists():
            partial = path.with_suffix(".partial")
            created = False
            try:
                with partial.open("xb") as target:
                    created = True
                    with urllib.request.urlopen(specification["url"], timeout=60) as response:
                        final = urllib.parse.urlsplit(response.geturl())
                        if final.scheme != "https" or final.netloc != "files.pythonhosted.org":
                            raise ValueError("Unexpected Python dependency redirect")
                        remaining = specification["size"]
                        while data := response.read(min(remaining + 1, 1024 * 1024)):
                            remaining -= len(data)
                            if remaining < 0:
                                raise ValueError("Python dependency exceeds its declared size")
                            target.write(data)
                if partial.stat().st_size != specification["size"] or digest(partial) != specification["sha256"]:
                    raise ValueError("Python dependency download digest mismatch")
                partial.rename(path)
            finally:
                if created and partial.exists():
                    partial.unlink()
        if path.is_symlink() or path.stat().st_size != specification["size"] or digest(path) != specification["sha256"]:
            raise ValueError("Cached Python dependency digest mismatch")
    return path


def stage_wheels(name, destination, *, owner):
    for specification in config().get("python_wheels", {}).get(name, []):
        path = wheel_path(specification)
        distribution = specification["distribution"].replace("-", "_")
        metadata = f"{distribution}-{specification['version']}.dist-info"
        allowed = {specification["import"], metadata}
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", specification["import"]):
            raise ValueError("Invalid wheel import package")
        root = destination / "usr/lib/cos/python"
        payload = path.read_bytes()
        if len(payload) != specification["size"] or hashlib.sha256(payload).hexdigest() != specification["sha256"]:
            raise ValueError("Python dependency snapshot digest mismatch")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
            if len(set(names)) != len(names) or sum(member.file_size for member in archive.infolist()) > 50_000_000:
                raise ValueError("Duplicate or oversized Python wheel payload")
            wheel = archive.read(f"{metadata}/WHEEL").decode()
            if "Root-Is-Purelib: true" not in wheel or "Tag: py3-none-any" not in wheel:
                raise ValueError("Architecture-all package requires a pure Python wheel")
            if not any(value.startswith(metadata + "/") and Path(value).name.upper().startswith("LICENSE")
                       for value in names):
                raise ValueError("Python wheel must retain its upstream license")
            for member in archive.infolist():
                relative = relative_path(member.filename.rstrip("/"))
                if relative.parts[0] not in allowed or stat.S_IFMT(member.external_attr >> 16) not in (
                    0, stat.S_IFREG, stat.S_IFDIR,
                ):
                    raise ValueError("Python wheel contains an unowned path or special file")
                target = root / relative
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output)
                    target.chmod(0o644)
                    if relative.parts[0] == metadata and relative.name.upper().startswith("LICENSE"):
                        license_file = destination / "usr/share/doc" / owner / "licenses" / (
                            specification["distribution"]
                        ) / relative.name
                        license_file.parent.mkdir(parents=True, exist_ok=True)
                        license_file.write_bytes(archive.read(member))
