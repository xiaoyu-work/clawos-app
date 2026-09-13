"""Real bounded plans and direct MCP contracts against synthetic OS authority."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import errno
import io
import json
import os
from pathlib import Path
import stat
import sys
import threading
from types import SimpleNamespace
from unittest import mock

import pytest

from claw_os_sdk.generated import validate_file_change_plan
from claw_os_sdk.objects import parse_reference
from test_support import (
    authenticated_mcp_params, load_local_module, mcp_process, unit_policy_bridge,
)


APP_DIR = Path(__file__).parent
plans = load_local_module(APP_DIR / "file_plans.py", "claw_test_fs_file_plans")
main = load_local_module(APP_DIR / "main.py", "claw_test_fs_main_for_plans")
from _shared import atomic

REAL_REPLACE_FILE = plans.file_changes.replace_file
REAL_SNAPSHOT = plans.snapshot.snapshot


@pytest.fixture
def environment(tmp_path, monkeypatch):
    data = tmp_path / "app-data"
    data.mkdir(mode=0o700)
    target = tmp_path / "document.txt"
    target.write_text("before\n", encoding="utf-8")
    monkeypatch.setenv("COS_DATA_DIR", str(data))
    require = mock.Mock()
    snapshot = mock.create_autospec(REAL_SNAPSHOT, return_value=None)
    monkeypatch.setattr(plans.policy, "require", require)
    monkeypatch.setattr(plans.snapshot, "snapshot", snapshot)

    def replace(path, expected, content, *, session_id):
        assert Path(path).is_relative_to(tmp_path)
        assert session_id
        current, before = plans._read_target(path)
        if current != expected:
            raise plans.file_changes.FileChangeError("synthetic target conflict")
        changed = expected is None or before.encode("utf-8") != content
        if changed:
            mode = stat.S_IMODE(expected["mode"]) if expected else 0o600
            atomic.atomic_write_bytes(path, content, mode=mode, strict=True)
        return {
            "path": path, "bytes": len(content), "changed": changed,
            "sha256": plans._hash(content),
        }

    rpc = mock.create_autospec(REAL_REPLACE_FILE, side_effect=replace)
    monkeypatch.setattr(plans.file_changes, "replace_file", rpc)
    return SimpleNamespace(
        root=tmp_path, data=data, target=target,
        require=require, snapshot=snapshot, rpc=rpc, replace=replace,
    )


def prepare(environment, content="after\n", *, target=None, ttl=3600):
    return plans.plan_write(str(target or environment.target), content, ttl)


def apply(plan, **overrides):
    arguments = {
        "path": plan["path"], "plan": plan["plan_id"], "review": plan["review"],
        "confirm": True, "session_id": "test-session",
    }
    return plans.plan_apply(**(arguments | overrides))


def stored(plan):
    return Path(plans._bucket(plan["path"]), plan["plan_id"] + ".json")


def expect_error(code, function, *args, **kwargs):
    with pytest.raises(plans.PlanError) as error:
        function(*args, **kwargs)
    assert error.value.code == code
    return str(error.value)


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("COS_APP_MANIFEST", str(APP_DIR / "app.json"))
    with mock.patch.dict(sys.modules, {"main": main, "file_plans": plans}):
        return load_local_module(APP_DIR / "server.py", "claw_test_fs_plan_server")


def call(server, name, arguments, *, session="test-session"):
    params = authenticated_mcp_params({"name": f"fs.{name}", "arguments": arguments})
    context = params["_meta"]["claw-os.dev/call-context"]
    if session is None:
        context.pop("session_id")
    else:
        context["session_id"] = session
    return server.app._handle_request("tools/call", params, True)


def test_prepare_produces_real_diff_private_data_and_object_reference(environment):
    plan = prepare(environment)
    validate_file_change_plan(plan)
    assert environment.target.read_text() == "before\n"
    assert plan["state"] == "draft"
    assert "-before\n+after\n" in plan["diff"]
    assert plan["would_change"] is True
    assert plan["after_sha256"] == plans._hash(b"after\n")
    assert parse_reference(plan["reference"]) == {
        "app_id": "fs", "object_type": "change-plan",
        "object_id": str(environment.target), "revision": plan["plan_id"],
    }
    assert "before_text" not in plan and "after_text" not in plan
    assert stat.S_IMODE(stored(plan).stat().st_mode) == 0o600
    assert stat.S_IMODE(stored(plan).parent.stat().st_mode) == 0o700
    environment.require.assert_has_calls([
        mock.call("fs.read", path=str(environment.target)),
        mock.call("data.db.write", name=plans.STORE_SCOPE),
    ])
    assert environment.require.call_count == 2
    environment.snapshot.assert_not_called()
    environment.rpc.assert_not_called()


def test_baseline_binds_bytes_identity_mode_and_nanosecond_timestamps(environment):
    plan = prepare(environment)
    before = json.loads(stored(plan).read_text())["before"]
    metadata = environment.target.stat()
    assert before == {
        "sha256": plans._hash(b"before\n"), "size": metadata.st_size,
        "device": metadata.st_dev, "inode": metadata.st_ino,
        "mode": metadata.st_mode, "modified_ns": metadata.st_mtime_ns,
        "changed_ns": metadata.st_ctime_ns,
    }


def test_missing_final_newlines_are_explicit(environment):
    environment.target.write_text("before")
    plan = prepare(environment, "after")
    assert "-before\n\\ No newline at end of file\n" in plan["diff"]
    assert "+after\n\\ No newline at end of file\n" in plan["diff"]


def test_diff_truncates_on_a_utf8_boundary_and_keeps_full_review_digest(environment):
    content = "é" * (plans.MAX_TEXT_BYTES // 2)
    plan = prepare(environment, content)
    assert plan["diff_truncated"]
    assert len(plan["diff"].encode("utf-8")) <= plans.MAX_DIFF_BYTES
    assert plan["after_sha256"] == plans._hash(content.encode("utf-8"))
    assert json.loads(stored(plan).read_text())["after_text"] == content
    validate_file_change_plan(plan)


def test_creation_needs_no_parent_visibility_or_write_during_prepare(environment):
    target = environment.root / "not-mounted" / "new.txt"
    plan = prepare(environment, "", target=target)
    assert plan["before_exists"] is False and plan["before_sha256"] is None
    assert plan["would_change"] is True
    assert not target.parent.exists()
    assert environment.require.call_args_list == [
        mock.call("fs.read", path=str(target)),
        mock.call("data.db.write", name=plans.STORE_SCOPE),
    ]
    environment.rpc.assert_not_called()


def test_apply_bracket_is_on_disk_before_snapshot_and_exact_broker_call(environment):
    plan = prepare(environment)

    def snapshot(*args, **kwargs):
        assert json.loads(stored(plan).read_text())["state"] == "applying"
        return "private-snapshot"

    def replace(*args, **kwargs):
        assert json.loads(stored(plan).read_text())["state"] == "applying"
        return environment.replace(*args, **kwargs)

    environment.snapshot.side_effect = snapshot
    environment.rpc.side_effect = replace
    result = apply(plan)
    validate_file_change_plan(result)
    assert result["state"] == "applied" and result["changed"] is True
    assert result["snapshot"] == "private-snapshot"
    assert environment.target.read_text() == "after\n"
    environment.snapshot.assert_called_once_with(
        plan["path"], "write", session_id="test-session"
    )
    baseline = json.loads(stored(plan).read_text())["before"]
    environment.rpc.assert_called_once_with(
        plan["path"], baseline, b"after\n", session_id="test-session"
    )
    expect_error("plan_consumed", apply, plan)
    environment.rpc.assert_called_once()


def test_absent_and_unchanged_apply_results_are_explicit(environment):
    new = environment.root / "new.txt"
    created = apply(prepare(environment, "", target=new))
    assert created["changed"] is True and new.read_bytes() == b""
    assert stat.S_IMODE(new.stat().st_mode) == 0o600
    unchanged = prepare(environment, "before\n")
    identity = environment.target.stat().st_ino
    assert unchanged["would_change"] is False
    assert apply(unchanged)["changed"] is False
    assert environment.target.stat().st_ino == identity


@pytest.mark.parametrize("mutation", ["content", "inode", "mode", "restored-mtime"])
def test_target_fingerprint_conflicts_are_consumed_not_overwritten(environment, mutation):
    plan = prepare(environment)
    original = environment.target.stat()
    if mutation == "inode":
        replacement = environment.root / "replacement"
        replacement.write_bytes(environment.target.read_bytes())
        os.chmod(replacement, stat.S_IMODE(original.st_mode))
        os.utime(replacement, ns=(original.st_atime_ns, original.st_mtime_ns))
        replacement.replace(environment.target)
    elif mutation == "mode":
        environment.target.chmod(stat.S_IMODE(original.st_mode) ^ stat.S_IXUSR)
    else:
        environment.target.write_text("extern\n")
        if mutation == "restored-mtime":
            os.utime(environment.target, ns=(original.st_atime_ns, original.st_mtime_ns))
    before_apply = environment.target.read_bytes()
    expect_error("plan_conflict", apply, plan)
    assert environment.target.read_bytes() == before_apply
    assert json.loads(stored(plan).read_text())["state"] == "conflicted"
    expect_error("plan_consumed", apply, plan)
    environment.rpc.assert_not_called()
    environment.snapshot.assert_not_called()


@pytest.mark.parametrize("kind", ["fifo", "directory"])
def test_target_becoming_unsupported_is_also_a_non_replayable_conflict(environment, kind):
    plan = prepare(environment)
    environment.target.unlink()
    if kind == "fifo":
        os.mkfifo(environment.target)
    else:
        environment.target.mkdir()
    expect_error("plan_conflict", apply, plan)
    expect_error("plan_consumed", apply, plan)
    environment.rpc.assert_not_called()


def test_changed_proposal_cannot_reuse_an_old_review(environment):
    plan = prepare(environment)
    record = json.loads(stored(plan).read_text())
    record["after_text"] = "different unreviewed content"
    record["review"] = plans._review(record)
    stored(plan).write_text(json.dumps(record))
    expect_error("plan_conflict", apply, plan)
    expect_error("plan_consumed", apply, plan, review=record["review"])
    assert environment.target.read_text() == "before\n"
    environment.rpc.assert_not_called()


def test_lost_response_after_replacement_persists_unknown_outcome_without_replay(environment):
    plan = prepare(environment)

    def replace_then_fail(*args, **kwargs):
        environment.replace(*args, **kwargs)
        raise plans.file_changes.FileChangeError("lost response after replacement")

    environment.rpc.side_effect = replace_then_fail
    message = expect_error("plan_indeterminate", apply, plan)
    assert "lost response" in message
    assert environment.target.read_text() == "after\n"
    record = json.loads(stored(plan).read_text())
    assert record["state"] == "indeterminate" and record["changed"] is None
    assert record["applied_at"] is None and "lost response" in record["diagnostic"]
    expect_error("plan_indeterminate", apply, plan)
    environment.rpc.assert_called_once()


@pytest.mark.parametrize("state", ["applying", "indeterminate"])
def test_existing_unknown_bracket_never_replays(environment, state):
    plan = prepare(environment)
    record = json.loads(stored(plan).read_text())
    record["state"] = state
    stored(plan).write_text(json.dumps(record))
    expect_error("plan_indeterminate", apply, plan)
    environment.rpc.assert_not_called()


def test_uncertain_diagnostics_stay_bounded(environment):
    plan = prepare(environment)
    environment.rpc.side_effect = plans.file_changes.FileChangeError("é" * 3000)
    expect_error("plan_indeterminate", apply, plan)
    record = json.loads(stored(plan).read_text())
    assert "[truncated]" in record["diagnostic"]
    assert len(record["diagnostic"].encode("utf-8")) <= 4096
    assert record["state"] == "indeterminate"


@pytest.mark.parametrize("result", [None, {}, {"changed": False}])
def test_malformed_broker_results_never_become_success(environment, result):
    plan = prepare(environment)
    environment.rpc.side_effect = None
    environment.rpc.return_value = result
    expect_error("plan_indeterminate", apply, plan)
    expect_error("plan_indeterminate", apply, plan)
    environment.rpc.assert_called_once()


def test_applied_record_failure_is_indeterminate_even_if_target_changed(environment, monkeypatch):
    plan = prepare(environment)
    save = plans._save

    def fail_final(directory, record):
        if record["state"] == "applied":
            raise OSError("final record failed")
        return save(directory, record)

    monkeypatch.setattr(plans, "_save", fail_final)
    expect_error("plan_indeterminate", apply, plan)
    assert environment.target.read_text() == "after\n"
    assert json.loads(stored(plan).read_text())["state"] == "indeterminate"


def test_failed_unknown_record_preserves_original_applying_bracket(environment, monkeypatch):
    plan = prepare(environment)
    save = plans._save

    def fail_final(directory, record):
        if record["state"] in ("applied", "indeterminate"):
            raise OSError("final record failed")
        return save(directory, record)

    monkeypatch.setattr(plans, "_save", fail_final)
    message = expect_error("plan_indeterminate", apply, plan)
    assert "persistence" in message
    assert json.loads(stored(plan).read_text())["state"] == "applying"
    assert environment.target.read_text() == "after\n"
    expect_error("plan_indeterminate", apply, plan)
    environment.rpc.assert_called_once()


def test_applying_fsync_failure_stops_before_snapshot_or_broker(environment, monkeypatch):
    plan = prepare(environment)

    def fail_sync(*args, **kwargs):
        raise OSError("directory sync failed")

    monkeypatch.setattr(atomic, "_fsync_dir", fail_sync)
    with pytest.raises(OSError, match="sync failed"):
        apply(plan)
    assert environment.target.read_text() == "before\n"
    assert json.loads(stored(plan).read_text())["state"] == "applying"
    expect_error("plan_indeterminate", apply, plan)
    environment.snapshot.assert_not_called()
    environment.rpc.assert_not_called()


def test_new_directory_ancestors_are_synced_before_prepare_reports_success(environment, monkeypatch):
    synced = []
    original = plans._fsync_dir

    def record_sync(path, *, strict=False):
        synced.append((path, strict))
        return original(path, strict=strict)

    monkeypatch.setattr(plans, "_fsync_dir", record_sync)
    prepare(environment)
    assert (str(environment.data), True) in synced
    assert (str(environment.data / "file-change-plans"), True) in synced


def test_snapshot_failure_keeps_unknown_bracket_and_skips_broker(environment):
    plan = prepare(environment)
    environment.snapshot.side_effect = OSError("snapshot failed")
    expect_error("plan_indeterminate", apply, plan)
    assert environment.target.read_text() == "before\n"
    environment.rpc.assert_not_called()


@pytest.mark.parametrize("value", ["", None, 1, True])
def test_apply_requires_authenticated_session_without_ambient_fallback(environment, value, monkeypatch):
    plan = prepare(environment)
    monkeypatch.setenv("COS_SESSION", "stale-service-session")
    environment.require.reset_mock()
    expect_error("plan_context", apply, plan, session_id=value)
    environment.require.assert_not_called()
    environment.rpc.assert_not_called()
    assert json.loads(stored(plan).read_text())["state"] == "draft"


@pytest.mark.parametrize("confirm", [False, "true", 1, None])
def test_confirmation_is_explicit_boolean_before_policy(environment, confirm):
    plan = prepare(environment)
    environment.require.reset_mock()
    expect_error("invalid_args", apply, plan, confirm=confirm)
    expect_error("invalid_args", plans.plan_prune, plan["path"], confirm)
    environment.require.assert_not_called()
    environment.rpc.assert_not_called()


@pytest.mark.parametrize("content", [None, 1, b"bytes", "x\0y", "\ud800", "x" * 65537])
def test_content_validation_precedes_policy(environment, content):
    with pytest.raises(plans.PlanError):
        prepare(environment, content)
    environment.require.assert_not_called()
    environment.rpc.assert_not_called()
    assert not list(environment.data.iterdir())


@pytest.mark.parametrize("value", [True, "60", 60.0, 59, 86401, None])
def test_lifetime_is_bounded_typed_integer_before_policy(environment, value):
    expect_error("invalid_args", prepare, environment, ttl=value)
    environment.require.assert_not_called()


@pytest.mark.parametrize("suffix", ["*", "[1]", "\ud800", "/../other", "\0"])
def test_nonliteral_paths_fail_before_policy(environment, suffix):
    expect_error(
        "invalid_args", plans.plan_write, str(environment.target) + suffix, "content"
    )
    environment.require.assert_not_called()


@pytest.mark.parametrize("path", ["relative", "/", "", None, 12])
def test_invalid_paths_fail_before_policy(environment, path):
    expect_error("invalid_args", plans.plan_write, path, "content")
    environment.require.assert_not_called()


def test_expired_plans_are_visible_but_never_applied(environment, monkeypatch):
    plan = prepare(environment, ttl=60)
    monkeypatch.setattr(plans, "_now", lambda: plans._seconds(plan["expires_at"]))
    expect_error("plan_expired", apply, plan)
    assert plans.plan_show(plan["path"], plan["plan_id"])["state"] == "expired"
    environment.rpc.assert_not_called()


def test_show_uses_latest_plan_and_fresh_target_read_authority(environment, monkeypatch):
    monkeypatch.setattr(plans, "_now", lambda: 1_700_000_000)
    older = prepare(environment, "older")
    monkeypatch.setattr(plans, "_now", lambda: 1_700_000_001)
    newer = prepare(environment, "newer")
    environment.require.reset_mock()
    assert plans.plan_show(newer["path"])["plan_id"] == newer["plan_id"]
    assert environment.require.call_args_list == [
        mock.call("fs.read", path=newer["path"]),
        mock.call("data.db.read", name=plans.STORE_SCOPE),
    ]
    assert plans.plan_show(older["path"], older["plan_id"])["diff"] == older["diff"]
    environment.require.side_effect = PermissionError("read denied")
    with pytest.raises(PermissionError, match="read denied"):
        plans.plan_show(newer["path"])


def test_denied_apply_has_no_effect_and_preserves_draft(environment):
    plan = prepare(environment)

    def authorize(verb, **scope):
        if verb == "fs.write":
            raise PermissionError("exact write denied")

    environment.require.side_effect = authorize
    with pytest.raises(PermissionError, match="exact write denied"):
        apply(plan)
    assert json.loads(stored(plan).read_text())["state"] == "draft"
    assert environment.target.read_text() == "before\n"
    environment.rpc.assert_not_called()
    environment.snapshot.assert_not_called()


@pytest.mark.parametrize("kind", ["hardlink", "fifo", "directory", "binary", "large", "xattr"])
def test_unsupported_targets_are_not_read_as_ordinary_text(environment, kind):
    if kind == "hardlink":
        os.link(environment.target, environment.root / "alias")
    elif kind == "fifo":
        environment.target.unlink()
        os.mkfifo(environment.target)
    elif kind == "directory":
        environment.target.unlink()
        environment.target.mkdir()
    elif kind == "binary":
        environment.target.write_bytes(b"\xff")
    elif kind == "large":
        environment.target.write_bytes(b"x" * (plans.MAX_TEXT_BYTES + 1))
    else:
        os.setxattr(environment.target, "user.plan-fixture", b"kept")
    expect_error("unsupported_file", prepare, environment)
    environment.rpc.assert_not_called()


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "public", "fifo", "directory"])
def test_stored_records_require_private_regular_single_link_files(environment, kind):
    plan = prepare(environment)
    record = stored(plan)
    if kind == "hardlink":
        os.link(record, environment.root / "alias")
    elif kind == "public":
        record.chmod(0o644)
    else:
        record.unlink()
        if kind == "symlink":
            record.symlink_to(environment.target)
        elif kind == "directory":
            record.mkdir()
        else:
            os.mkfifo(record)
    with pytest.raises((plans.PlanError, OSError)):
        apply(plan)
    assert environment.target.read_text() == "before\n"
    environment.rpc.assert_not_called()


@pytest.mark.parametrize("source", ["target", "record"])
@pytest.mark.parametrize("failure", ["directory", "stream"])
def test_rejected_reads_close_owned_descriptors(environment, monkeypatch, source, failure):
    if source == "target":
        path = environment.target
        read = lambda: plans._read_target(str(path))
        code = "unsupported_file"
    else:
        plan = prepare(environment)
        path = stored(plan)
        read = lambda: plans._load(str(path.parent), plan["path"], plan["plan_id"])
        code = "plan_storage"
    if failure == "directory":
        path.unlink()
        path.mkdir()
    else:
        monkeypatch.setattr(
            plans.os, "fdopen", mock.Mock(side_effect=OSError("synthetic stream failure"))
        )
    opened = []
    original_open = os.open

    def track_open(filename, flags, *args, **kwargs):
        descriptor = original_open(filename, flags, *args, **kwargs)
        if os.fspath(filename) == str(path):
            opened.append(descriptor)
        return descriptor

    monkeypatch.setattr(plans.os, "open", track_open)
    if failure == "directory":
        expect_error(code, read)
    else:
        with pytest.raises(OSError, match="synthetic stream failure"):
            read()
    assert len(opened) == 1
    with pytest.raises(OSError) as closed:
        os.fstat(opened[0])
    assert closed.value.errno == errno.EBADF


@pytest.mark.parametrize("kind", ["extra-field", "bad-baseline", "bad-lifecycle", "duplicate", "oversized"])
def test_corrupt_records_are_errors_not_repaired_or_trusted(environment, kind):
    plan = prepare(environment)
    path = stored(plan)
    record = json.loads(path.read_text())
    if kind == "extra-field":
        record["unexpected"] = True
    elif kind == "bad-baseline":
        record["before_text"] = "forged baseline"
    elif kind == "bad-lifecycle":
        record["state"] = "applied"
    contents = json.dumps(record)
    if kind == "duplicate":
        contents = contents[:-1] + ', "state":"draft"}'
    elif kind == "oversized":
        contents = " " * (plans.MAX_PLAN_BYTES + 1)
    path.write_text(contents)
    expect_error("plan_invalid", apply, plan)
    assert path.read_text() == contents
    environment.rpc.assert_not_called()


def test_cross_target_identity_cannot_select_another_targets_record(environment):
    plan = prepare(environment)
    other = environment.root / "other.txt"
    other.write_text("other")
    with pytest.raises(FileNotFoundError):
        apply(plan, path=str(other))
    assert other.read_text() == "other"
    environment.rpc.assert_not_called()


def test_plan_limit_requires_explicit_retired_record_pruning(environment, monkeypatch):
    monkeypatch.setattr(plans, "MAX_PLANS", 2)
    prepare(environment, "one")
    prepare(environment, "two")
    expect_error("plan_limit", prepare, environment, "three")
    result = plans.plan_prune(str(environment.target), True, 0)
    assert result == {"removed": [], "kept": 2, "target_changed": False}


def test_prune_preserves_live_and_unknown_plans_and_never_changes_target(environment):
    consumed = prepare(environment)
    apply(consumed)
    for state in ("draft", "applying", "indeterminate"):
        plan = prepare(environment, state)
        record = json.loads(stored(plan).read_text())
        record["state"] = state
        stored(plan).write_text(json.dumps(record))
    expired = prepare(environment, "expired")
    record = json.loads(stored(expired).read_text())
    record["state"] = "expired"
    stored(expired).write_text(json.dumps(record))
    result = plans.plan_prune(str(environment.target), True, 0)
    assert set(result["removed"]) == {consumed["plan_id"], expired["plan_id"]}
    assert result["kept"] == 3 and result["target_changed"] is False
    assert environment.target.read_text() == "after\n"


def test_cooperative_concurrent_apply_is_serialized_and_never_replayed(environment):
    plan = prepare(environment)
    entered, release = threading.Event(), threading.Event()

    def blocked_replace(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return environment.replace(*args, **kwargs)

    environment.rpc.side_effect = blocked_replace
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(apply, plan)
        try:
            assert entered.wait(5)
            second = executor.submit(apply, plan)
            with pytest.raises(FutureTimeout):
                second.result(timeout=0.1)
        finally:
            release.set()
        assert first.result(timeout=5)["state"] == "applied"
        expect_error("plan_consumed", second.result, timeout=5)
    environment.rpc.assert_called_once()


def test_mcp_plan_content_is_explicit_and_never_reads_protocol_stdin(server, environment, monkeypatch):
    unreadable = mock.Mock(spec=io.TextIOBase)
    unreadable.read.side_effect = AssertionError("protocol stdin was read")
    monkeypatch.setattr(sys, "stdin", unreadable)
    result = call(server, "plan_write", {"path": str(environment.target)})
    assert result["isError"] is True
    environment.require.assert_not_called()
    result = call(server, "plan_write", {"path": str(environment.target), "content": ""})
    assert result["isError"] is False and result["structuredContent"]["after_bytes"] == 0
    unreadable.read.assert_not_called()


def test_mcp_errors_keep_plan_code_and_error_flag(server, environment):
    plan = prepare(environment)
    environment.target.write_text("external edit")
    result = call(server, "plan_apply", {
        "path": plan["path"], "plan": plan["plan_id"], "review": plan["review"],
        "confirm": True,
    })
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "plan_conflict"
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]


def test_mcp_apply_uses_each_authenticated_session_not_process_environment(server, environment, monkeypatch):
    monkeypatch.setenv("COS_SESSION", "stale-service-session")
    for session in ("first-session", "second-session"):
        plan = prepare(environment, session)
        result = call(server, "plan_apply", {
            "path": plan["path"], "plan": plan["plan_id"], "review": plan["review"],
            "confirm": True,
        }, session=session)
        assert result["isError"] is False, result
        assert environment.rpc.call_args.kwargs == {"session_id": session}
        assert environment.snapshot.call_args.kwargs == {"session_id": session}
    plan = prepare(environment)
    environment.require.reset_mock()
    result = call(server, "plan_apply", {
        "path": plan["path"], "plan": plan["plan_id"], "review": plan["review"],
        "confirm": True,
    }, session=None)
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "plan_context"
    environment.require.assert_not_called()
    assert environment.rpc.call_count == 2


def test_mcp_never_accepts_a_forged_session_argument(server, environment):
    plan = prepare(environment)
    environment.require.reset_mock()
    result = call(server, "plan_apply", {
        "path": plan["path"], "plan": plan["plan_id"], "review": plan["review"],
        "confirm": True, "session_id": "forged",
    })
    assert result["isError"] is True
    environment.require.assert_not_called()
    environment.rpc.assert_not_called()


def test_public_mcp_prepare_show_and_prune_use_the_declared_entrypoint(environment, unit_policy_bridge):
    env = {
        "PATH": os.defpath, "PYTHONPATH": os.environ["PYTHONPATH"],
        "CLAW_COS_BIN": os.environ["CLAW_COS_BIN"], "COS_DATA_DIR": str(environment.data),
    }
    with mcp_process(APP_DIR, env=env) as request:
        result = request("tools/call", authenticated_mcp_params({
            "name": "fs.plan_write",
            "arguments": {"path": str(environment.target), "content": "after\n"},
        }))
        assert not result["isError"], result
        plan = result["structuredContent"]
        shown = request("tools/call", authenticated_mcp_params({
            "name": "fs.plan_show",
            "arguments": {"path": plan["path"], "plan": plan["plan_id"]},
        }))
        assert not shown["isError"] and shown["structuredContent"] == plan
        pruned = request("tools/call", authenticated_mcp_params({
            "name": "fs.plan_prune",
            "arguments": {"path": plan["path"], "confirm": True, "keep": 0},
        }))
        assert not pruned["isError"]
        assert pruned["structuredContent"] == {
            "removed": [], "kept": 1, "target_changed": False,
        }
    assert environment.target.read_text() == "before\n"
