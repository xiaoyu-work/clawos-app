"""Strict plan persistence is additive to the shared legacy atomic helpers."""

import json
import os
from types import SimpleNamespace
from unittest import mock

import pytest

from _shared import atomic


def test_strict_file_fsync_failure_preserves_original_and_removes_staging_file(tmp_path):
    directory = tmp_path / "payload"
    directory.mkdir()
    target = directory / "record"
    target.write_bytes(b"before")
    with mock.patch.object(atomic.os, "fsync", side_effect=OSError("fsync failed")):
        with pytest.raises(OSError, match="fsync failed"):
            atomic.atomic_write_bytes(str(target), b"after", strict=True)
    assert target.read_bytes() == b"before"
    assert list(directory.iterdir()) == [target]


def test_strict_directory_fsync_failure_is_not_reported_as_success(tmp_path):
    target = tmp_path / "record"
    target.write_bytes(b"before")
    with mock.patch.object(
        atomic.os, "fsync", side_effect=[None, OSError("directory fsync failed")]
    ):
        with pytest.raises(OSError, match="directory fsync failed"):
            atomic.atomic_write_bytes(str(target), b"after", strict=True)
    assert target.read_bytes() == b"after"


def test_strict_directory_open_failure_propagates(tmp_path):
    with mock.patch.object(atomic.os, "open", side_effect=OSError("cannot open directory")):
        with pytest.raises(OSError, match="cannot open directory"):
            atomic._fsync_dir(str(tmp_path), strict=True)
        atomic._fsync_dir(str(tmp_path))


@pytest.mark.parametrize("kind", ["existing", "symlink"])
def test_strict_staging_never_truncates_a_colliding_path(tmp_path, kind):
    target = tmp_path / "record"
    target.write_bytes(b"before")
    collision = tmp_path / f"record.tmp.{os.getpid()}.deadbeef"
    if kind == "existing":
        collision.write_bytes(b"other")
    else:
        collision.symlink_to(target)
    with mock.patch.object(atomic.uuid, "uuid4", return_value=SimpleNamespace(hex="deadbeef")):
        with pytest.raises(FileExistsError):
            atomic.atomic_write_bytes(str(target), b"after", strict=True)
    assert target.read_bytes() == b"before"
    if kind == "existing":
        assert collision.read_bytes() == b"other"


def test_strict_json_uses_private_mode_and_valid_utf8(tmp_path):
    target = tmp_path / "record"
    atomic.atomic_write_json(str(target), {"content": "é"}, mode=0o600, strict=True)
    assert json.loads(target.read_text()) == {"content": "é"}
    assert target.stat().st_mode & 0o777 == 0o600


def test_legacy_replacement_keeps_best_effort_behavior(tmp_path):
    target = tmp_path / "record"
    with mock.patch.object(atomic.os, "fsync", side_effect=OSError("unsupported")):
        atomic.atomic_write_bytes(str(target), b"legacy")
    assert target.read_bytes() == b"legacy"


def test_existing_atomic_create_remains_no_replace(tmp_path):
    directory = tmp_path / "payload"
    directory.mkdir()
    target = directory / "record"
    atomic.atomic_create_bytes(str(target), b"created", mode=0o600)
    with pytest.raises(FileExistsError):
        atomic.atomic_create_bytes(str(target), b"not a replacement")
    assert target.read_bytes() == b"created"
    assert target.stat().st_mode & 0o777 == 0o600
    assert list(directory.iterdir()) == [target]
