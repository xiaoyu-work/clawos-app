"""Native Terminal identity, exact grants and descriptor staging."""

import json
from pathlib import Path

from test_support import load_local_module

PRODUCT = Path(__file__).resolve().parents[2]
ROOT = PRODUCT.parents[1]


def test_native_identity_keeps_three_exact_independent_grants():
    manifest = json.loads(Path(__file__).with_name("app.json").read_text())
    assert (manifest["id"], manifest["runtime"], manifest["schema_version"]) == (
        "cosmic-term", "binary", 2,
    )
    assert manifest["mcp"]["entry"] == "/usr/bin/cosmic-term"
    tools = {tool["name"]: tool for tool in manifest["mcp"]["tools"]}
    assert set(tools) == {"term.run", "term.which", "term.open"}
    assert [(tool, [(need["verb"], need["scope"]) for need in tools[tool]["needs"]])
            for tool in tools] == [
        ("term.run", [("proc.spawn", {"kind": "from-arg", "arg": "command"})]),
        ("term.which", [("fs.meta", {"kind": "from-arg", "arg": "program"})]),
        ("term.open", [("proc.spawn", {
            "kind": "fixed", "scope": {"kind": "name", "value": "cosmic-term"},
        })]),
    ]
    assert "ai" not in manifest


def test_staging_keeps_exec_and_native_terminal_separate(tmp_path):
    stage = load_local_module(ROOT / "tools/stage.py", "terminal_stage")
    assert set(stage.stage("terminal", tmp_path)) == {"exec", "cosmic-term"}
    installed = tmp_path / "usr/lib/cos/apps"
    assert {p.name for p in (installed / "cosmic-term").iterdir()} == {"app.json"}
    assert (installed / "exec/main.py").read_bytes() == (PRODUCT / "apps/exec/main.py").read_bytes()
    assert not (installed / "cosmic-term/proc").exists()
