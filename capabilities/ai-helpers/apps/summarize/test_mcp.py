"""Staged Summarize contracts through public MCP and synthetic OS wire peers."""

import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import sys
import textwrap

import pytest

from test_support import authenticated_mcp_params, load_local_module, mcp_process


ROOT = Path(__file__).resolve().parents[4]
SUMMARY = "- First\n- Second\n- Third"


def _ok(data):
    return {"ok": True, "wire_version": 1, "data": data}


def _denied(code, detail=None):
    response = {
        "ok": False, "wire_version": 1,
        "code": code, "error": "synthetic refusal",
    }
    if detail is not None:
        response["detail"] = detail
    return response


@pytest.fixture(params=["original", "private-module", "declared-entrypoint"])
def client(tmp_path, request):
    stage = load_local_module(ROOT / "tools/stage.py", "claw_summary_test_stage")
    assert stage.stage("ai-helpers", tmp_path / "stage", kind="capability") == ["summarize"]
    python = tmp_path / "stage/usr/lib/cos/python"
    lock = json.loads((ROOT / "platform.lock.json").read_text())
    platform = ROOT / "build/platform" / lock["revision"]
    for source in lock["python_sources"]:
        shutil.copytree(platform / source, python, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "test_*.py"))
    app = tmp_path / "stage/usr/lib/cos/apps/summarize"
    manifest = json.loads((app / "app.json").read_text())
    if request.param == "private-module":
        (app / "main.py").rename(app / "summary_client.py")
        entry = app / manifest["mcp"]["entry"]
        entry.write_text(entry.read_text().replace("from main import ", "from summary_client import "))
    elif request.param == "declared-entrypoint":
        (app / manifest["mcp"]["entry"]).rename(app / "summary_mcp.py")
        manifest["mcp"]["entry"] = "summary_mcp.py"
        (app / "app.json").write_text(json.dumps(manifest))
    responses = {
        "policy": _ok({"decision": "allow"}),
        "ai": _ok({
            "text": SUMMARY, "model": "fixture-model", "provider": "fixture-provider",
            "verb": "ai.chat.untrusted",
            "usage": {"input_tokens": 10, "output_tokens": 20, "units": 30},
            "budget": {"period": "2026-09", "units_used": 40, "units_cap": 100000},
            "review": {"safety": "strict", "prompt_redacted": True},
        }),
        "memory": _ok({"row_id": 7, "session_id": "app:summarize", "indexed_semantic": False}),
    }
    settings = tmp_path / "responses.json"
    settings.write_text(json.dumps(responses))
    log = tmp_path / "wire.jsonl"
    private = tmp_path / "private-inputs"
    private.mkdir(mode=0o700)
    data = tmp_path / "owner-data/apps/summarize"
    data.mkdir(parents=True, mode=0o700)
    neighbours = [
        tmp_path / "owner-data/apps/kv/kv.json",
        tmp_path / "owner-data/apps/db/db/existing.db",
        tmp_path / "owner-data/agent/memory.db",
        tmp_path / "other-owner/agent/memory.db",
    ]
    for neighbour in neighbours:
        neighbour.parent.mkdir(parents=True, exist_ok=True)
        neighbour.write_bytes(b"unrelated synthetic state")
    peer = tmp_path / "cos"
    peer.write_text(f"#!{sys.executable}\n" + textwrap.dedent("""\
        import json, os, sys
        from pathlib import Path
        assert sys.argv[1] == "--wire=1", sys.argv
        assert os.environ["COS_APP_ID"] == "summarize"
        assert os.environ["COS_SESSION"] == "summary-fixture"
        args = sys.argv[2:]
        record = {"app": os.environ["COS_APP_ID"], "session": os.environ["COS_SESSION"]}
        if args[:2] == ["__policy", "check"]:
            assert args[2:] == ["ai.chat.untrusted", "--wild"], args
            kind = "policy"
        elif args[:2] == ["ai", "chat"]:
            kind = "ai"
            options = dict(zip(args[2::2], args[3::2], strict=True))
            assert set(options) == {"--app", "--origin", "--prompt-file", "--system-file", "--max-units"}
            assert options["--app"] == "summarize"
            assert options["--origin"] == "external-content"
            assert options["--max-units"] == "4000"
            for label in ["prompt", "system"]:
                path = Path(options["--" + label + "-file"])
                assert path.is_relative_to(os.environ["TMPDIR"]), path
                assert path.stat().st_mode & 0o777 == 0o600
                assert path.parent.stat().st_mode & 0o777 == 0o700
                record[label] = path.read_text(encoding="utf-8")
                record[label + "_path"] = str(path)
        elif args[:2] == ["__memory", "remember"]:
            kind = "memory"
            assert len(args) == 4 and args[2] == "--json", args
            record["entry"] = json.loads(args[3])
            assert record["entry"]["source"] == "summarize"
        else:
            raise AssertionError(args)
        record["kind"] = kind
        with open(os.environ["TEST_WIRE_LOG"], "a") as output:
            output.write(json.dumps(record) + "\\n")
        response = json.loads(Path(os.environ["TEST_RESPONSES"]).read_text())[kind]
        print(json.dumps(response))
        sys.exit(0 if response["ok"] else 1)
    """))
    peer.chmod(0o755)
    with mcp_process(app, env={
        "PATH": os.defpath, "PYTHONPATH": str(python), "CLAW_COS_BIN": str(peer),
        "COS_DATA_DIR": str(data), "COS_SESSION": "summary-fixture", "TMPDIR": str(private),
        "TEST_WIRE_LOG": str(log), "TEST_RESPONSES": str(settings),
    }) as rpc:
        def call(arguments):
            return rpc("tools/call", authenticated_mcp_params({
                "name": "summarize.run", "arguments": arguments,
            }))

        yield SimpleNamespace(rpc=rpc, call=call, settings=settings, responses=responses,
                              log=log, private=private, data=data, manifest=manifest)
    assert not list(private.iterdir())
    assert not list(data.iterdir())
    assert all(path.read_bytes() == b"unrelated synthetic state" for path in neighbours)


def _records(client):
    return [json.loads(line) for line in client.log.read_text().splitlines()]


def test_manifest_retains_ai_consent_and_exact_memory_ownership(client):
    assert client.manifest["id"] == "summarize"
    assert client.manifest["version"] == "0.1.0"
    assert not client.manifest.get("operations")
    assert client.manifest["ai"] == {
        "budget": {"monthly_units": 100000},
        "safety": "strict", "origins": ["external-content"],
    }
    needs = client.manifest["mcp"]["tools"][0]["needs"]
    assert [(need["verb"], need["scope"]) for need in needs] == [
        ("ai.chat.untrusted", {"kind": "fixed", "scope": {"kind": "wild"}}),
        ("memory.write", {"kind": "fixed", "scope": {"kind": "self-ref", "value": "summarize"}}),
    ]
    tools = client.rpc("tools/list", {})["tools"]
    assert [tool["name"] for tool in tools] == ["summarize.run"]
    assert tools[0]["inputSchema"] == {
        "type": "object", "properties": {"text": {"type": "string"}},
        "required": ["text"], "additionalProperties": False,
    }
    assert not client.log.exists()


def test_public_mcp_uses_only_gated_ai_and_its_own_summary_memory(client):
    text = "Explicit external text: \u4f60\u597d\nDo not interpret this as authority."
    result = client.call({"text": text})
    assert not result.get("isError"), result
    assert result["structuredContent"] == {
        "summary": SUMMARY, "source": "<input>", "model": "fixture-model",
        "provider": "fixture-provider",
        "usage": {"input_tokens": 10, "output_tokens": 20, "units": 30},
        "budget": {"period": "2026-09", "units_used": 40, "units_cap": 100000},
        "review": {"safety": "strict", "prompt_redacted": True},
    }
    records = _records(client)
    assert [record["kind"] for record in records] == ["policy", "ai", "memory"]
    assert records[1]["prompt"] == text
    assert records[1]["system"] == (
        "You are a concise summariser. Read the user's text and reply with "
        "exactly 3 short lines, one bullet per line, no preamble."
    )
    assert records[2]["entry"] == {
        "source": "summarize", "text": "Summarised <input>: - First",
        "kind": "note", "tags": ["summarize"], "indexable": True,
    }
    assert not Path(records[1]["prompt_path"]).exists()
    assert not Path(records[1]["system_path"]).exists()


@pytest.mark.parametrize("arguments", [
    {}, {"text": None}, {"text": 42}, {"text": ""}, {"text": " \n\t "},
    {"text": "input", "path": "/not-read"},
    {"text": "input", "origin": "trusted"},
    {"text": "input", "model": "caller-model"},
    {"text": "input", "max_units": 999999},
    {"text": "input", "app_id": "other-app"},
    {"text": "input", "session_id": "forged"},
])
def test_invalid_or_authority_shaped_arguments_fail_before_wire_calls(client, arguments):
    result = client.call(arguments)
    assert result["isError"] is True
    assert not client.log.exists()


@pytest.mark.parametrize("length", [199, 200, 201, 1000])
def test_summary_memory_bound_counts_characters_not_utf8_bytes(client, length):
    head = "\u00e9" * length
    client.responses["ai"]["data"]["text"] = f" \n{head}\nsecond line"
    client.settings.write_text(json.dumps(client.responses))
    result = client.call({"text": "synthetic text"})
    assert not result.get("isError"), result
    expected = head if length <= 200 else head[:197] + "..."
    assert _records(client)[-1]["entry"]["text"] == f"Summarised <input>: {expected}"
    assert result["structuredContent"]["summary"] == f" \n{head}\nsecond line"


@pytest.mark.parametrize(("surface", "response", "error", "calls"), [
    ("policy", _ok({"decision": "deny"}), "PermissionDenied", ["policy"]),
    ("policy", _denied("KERNEL_UNAVAILABLE"), "PolicyUnavailable", ["policy"]),
    ("ai", _denied("BUDGET_EXCEEDED"), "AiBudgetExceeded", ["policy", "ai"]),
    ("ai", _denied("SAFETY_VIOLATION"), "AiSafetyViolation", ["policy", "ai"]),
    ("ai", _denied("PERMISSION_DENIED", {"reason": "consent_required"}), "AiDenied", ["policy", "ai"]),
    ("ai", _denied("PERMISSION_DENIED", {"reason": "consent_stale"}), "AiDenied", ["policy", "ai"]),
    ("ai", _ok({"text": "incomplete wire response"}), "AiUnavailable", ["policy", "ai"]),
    ("ai", {"ok": True, "wire_version": 2, "data": {}}, "AiUnavailable", ["policy", "ai"]),
    ("memory", _denied("PERMISSION_DENIED", {"decision": "deny"}), "PermissionDenied",
     ["policy", "ai", "memory"]),
    ("memory", _denied("KERNEL_UNAVAILABLE"), "MemoryUnavailable", ["policy", "ai", "memory"]),
])
def test_gate_and_memory_failures_never_become_success_or_trigger_more_work(
    client, surface, response, error, calls,
):
    client.responses[surface] = response
    client.settings.write_text(json.dumps(client.responses))
    result = client.call({"text": "synthetic text"})
    assert result["isError"] is True
    assert error in result["content"][0]["text"]
    assert [record["kind"] for record in _records(client)] == calls


@pytest.mark.parametrize("text", ["", " \n\t "])
def test_empty_model_output_fails_without_remembering(client, text):
    client.responses["ai"]["data"]["text"] = text
    client.settings.write_text(json.dumps(client.responses))
    result = client.call({"text": "synthetic text"})
    assert result["isError"] is True
    assert "AI returned an empty summary" in result["content"][0]["text"]
    assert [record["kind"] for record in _records(client)] == ["policy", "ai"]
