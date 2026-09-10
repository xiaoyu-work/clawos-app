"""Keep App delivery separate from OS authority, regardless of language or origin."""

from contextlib import contextmanager
import os
from pathlib import PurePosixPath
import posixpath
import stat
import subprocess
import tarfile
import tempfile


CONTROL_FILES = {"control", "md5sums"}
AUTHORITY_PATHS = tuple(PurePosixPath(path) for path in (
    "usr/local",
    "usr/lib/systemd/system", "usr/lib64/systemd/system",
    "usr/lib/systemd/system-generators", "usr/lib/systemd/system-environment-generators",
    "usr/lib/systemd/system-preset", "usr/lib/systemd/system-shutdown", "usr/lib/systemd/system-sleep",
    "usr/share/dbus-1/system-services", "usr/share/dbus-1/system.d",
    "usr/share/polkit-1", "usr/lib/polkit-1",
    "usr/lib/sysusers.d", "usr/lib/tmpfiles.d", "usr/share/factory",
    "usr/lib/udev", "usr/lib/modules", "usr/lib/modules-load.d", "usr/lib/modprobe.d",
    "usr/share/pam-configs", "usr/lib/security", "usr/lib/sudo",
    "usr/lib/apt", "usr/lib/dpkg", "usr/share/initramfs-tools",
    "usr/lib/NetworkManager/dispatcher.d", "usr/lib/networkd-dispatcher",
))
MAX_ENTRIES = 100_000
MAX_BYTES = 2 * 1024 * 1024 * 1024


def archive_path(value):
    if value.startswith("./"):
        value = value[2:]
    value = value.rstrip("/")
    if value in ("", "."):
        return PurePosixPath(".")
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or ".." in path.parts or "\\" in value or (
        len(value) > 4096 or len(path.parts) > 64
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError(f"Unsafe App package path: {value!r}")
    return path


def payload_path(path):
    if path == PurePosixPath("."):
        return
    if path.parts[0] != "usr" or any(path.is_relative_to(prefix) for prefix in AUTHORITY_PATHS):
        raise ValueError(f"App delivery cannot install state, grants or OS authority hooks: {path}")


def validate_install_tree(root, *, allow_control=True):
    for path in root.rglob("*"):
        relative = PurePosixPath(path.relative_to(root).as_posix())
        mode = path.lstat().st_mode
        if relative.parts[0] == "DEBIAN":
            if not allow_control or (
                relative != PurePosixPath("DEBIAN")
                and (len(relative.parts) != 2 or relative.name not in CONTROL_FILES or not stat.S_ISREG(mode))
            ):
                raise ValueError(f"App installer cannot supply Debian hooks or control metadata: {relative}")
        else:
            payload_path(relative)
        if mode & (stat.S_ISUID | stat.S_ISGID):
            raise ValueError(f"App delivery cannot confer setuid/setgid privilege: {relative}")
        if any(name.startswith(("security.", "system.posix_acl_"))
               for name in os.listxattr(path, follow_symlinks=False)):
            raise ValueError(f"App delivery cannot confer file capabilities or access ACLs: {relative}")


@contextmanager
def deb_archive(path, flag, environment, scratch):
    with tempfile.TemporaryFile(dir=scratch) as errors, subprocess.Popen(
        ["dpkg-deb", flag, str(path)], stdout=subprocess.PIPE, stderr=errors, env=environment,
    ) as process:
        assert process.stdout is not None
        finished = False
        try:
            with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
                yield archive
            if len(process.stdout.read(1024 * 1024 + 1)) > 1024 * 1024:
                raise ValueError("Unexpected trailing App archive output")
            finished = True
        finally:
            process.stdout.close()
            if not finished and process.poll() is None:
                process.terminate()
            code = process.wait()
            if finished and code:
                errors.seek(0)
                detail = errors.read(64 * 1024).decode(errors="replace").strip()
                raise ValueError(f"Cannot inspect App Debian archive: {detail or code}")


def validate_deb(path, *, environment, scratch):
    for flag, control in (("--ctrl-tarfile", True), ("--fsys-tarfile", False)):
        nodes, links = {}, {}
        total = 0
        with deb_archive(path, flag, environment, scratch) as archive:
            for member in archive:
                name = archive_path(member.name)
                if name == PurePosixPath(".") and not member.isdir():
                    raise ValueError("App package root must be a directory")
                if name in nodes or len(nodes) >= MAX_ENTRIES:
                    raise ValueError("Duplicate or excessive App package entries")
                total += member.size
                if total > (2 * 1024 * 1024 if control else MAX_BYTES):
                    raise ValueError("App package exceeds inspection limits")
                if member.uid or member.gid or member.mode & 0o6000 or (
                    not member.issym() and member.mode & 0o022
                ):
                    raise ValueError(f"App package has unsafe ownership or privilege-bearing modes: {name}")
                if any("xattr" in key or key.startswith("SCHILY.acl.") for key in member.pax_headers):
                    raise ValueError(f"App package cannot supply capabilities or access ACLs: {name}")
                if control:
                    if name != PurePosixPath(".") and (
                        len(name.parts) != 1 or name.name not in CONTROL_FILES or not member.isfile()
                    ):
                        raise ValueError(f"App package cannot supply maintainer/root hooks: {name}")
                else:
                    payload_path(name)
                if member.isdir():
                    kind = "directory"
                elif member.isfile():
                    kind = "file"
                elif not control and (member.issym() or member.islnk()):
                    kind = "symlink" if member.issym() else "hardlink"
                    if PurePosixPath(member.linkname).is_absolute() or "\\" in member.linkname:
                        raise ValueError(f"App package link escapes its payload: {name}")
                    target = archive_path(posixpath.normpath(
                        posixpath.join(str(name.parent), member.linkname) if member.issym() else member.linkname
                    ))
                    payload_path(target)
                    links[name] = target
                else:
                    raise ValueError(f"App package contains a special file: {name}")
                nodes[name] = kind
        if control and nodes.get(PurePosixPath("control")) != "file":
            raise ValueError("App package requires release-owned control metadata")
        for name, kind in nodes.items():
            if any(parent in nodes and nodes[parent] != "directory" for parent in name.parents):
                raise ValueError(f"App package entry has a non-directory ancestor: {name}")
            if kind == "hardlink" and nodes.get(links[name]) != "file":
                raise ValueError(f"App package hardlink has no owned regular target: {name}")
