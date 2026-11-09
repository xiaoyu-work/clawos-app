import json
import shutil
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parents[3]


def test_existing_identity_has_one_real_package_local_gui_and_mcp_entry():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/native_payload.py"), "clipboard", "--plan"],
        capture_output=True, text=True, check=True, timeout=15,
    )
    plan = json.loads(result.stdout)
    manifest = json.loads((APP / "app.json").read_text())
    assert manifest["id"] == "panel-clipboard"
    assert manifest["runtime"] == "binary"
    assert manifest["entry"] == manifest["mcp"]["entry"] == "bin/claw-applet-clipboard"
    assert plan["entrypoints"] == ["bin/claw-applet-clipboard"]
    assert plan["gui_command"] == ["/usr/local/bin/cos", "app", "panel-clipboard", "open"]
    assert manifest["desktop"]["single_instance"] is True
    assert manifest["desktop"]["panel_applet"] is True
    assert not (APP / "main.sh").exists()


def test_history_tools_keep_exact_grants_and_separate_selection_write():
    manifest = json.loads((APP / "app.json").read_text())
    tools = {tool["name"]: tool for tool in manifest["mcp"]["tools"]}
    assert set(tools) == {"history.list", "history.restore", "history.remove", "history.clear"}
    scopes = {
        name: [(need["verb"], need["scope"]["scope"]["value"]) for need in tool["needs"]]
        for name, tool in tools.items()
    }
    assert scopes == {
        "history.list": [("clipboard.read", "history")],
        "history.restore": [("clipboard.read", "history"), ("clipboard.write", "history"),
                            ("clipboard.write", "selection")],
        "history.remove": [("clipboard.read", "history"), ("clipboard.write", "history")],
        "history.clear": [("clipboard.write", "history")],
    }
    assert tools["history.list"]["args"] == []
    assert tools["history.clear"]["args"] == [
        {"name": "confirm", "kind": "bool", "required": True, "choices": [True], "binding": "flag"},
    ]
    assert all(need["scope"]["kind"] == "fixed" for tool in tools.values() for need in tool["needs"])
    assert [(need["verb"], need["scope"]["scope"]["value"])
            for need in manifest["operations"]["open"]["needs"]] == [
        ("clipboard.read", "history"), ("clipboard.write", "history"),
        ("clipboard.write", "selection"),
    ]


def test_web_history_is_explicit_text_only_and_calls_only_owning_tools():
    node = shutil.which("node")
    assert node, "Clipboard Web workflow tests require the existing Node runner"
    script = r"""
const fs = require("node:fs"), vm = require("node:vm"), assert = require("node:assert/strict");
class Element {
  constructor(tag = "div") { this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.hidden = false; this.disabled = false; this.attributes = {}; this.textContent = ""; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  setAttribute(name, value) { this.attributes[name] = value; }
  querySelectorAll(tag) { return this.children.filter((item) => item.tagName === tag.toUpperCase()); }
  set innerHTML(_) { throw Error("HTML interpretation is forbidden"); }
}
const html = fs.readFileSync(process.argv[2], "utf8");
const nodes = Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map((match) => [match[1], new Element()]));
const id = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
const preview = "<img src=x onerror=alert(1)> private text";
const app = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
app.tools = app.mcp.tools;
const calls = [], reviews = [];
let unavailable = false;
const ClawApp = {
  ready: Promise.resolve(app),
  tool: (owner, name) => owner.tools.find((tool) => tool.name === name),
  call: async (name, args) => {
    assert.ok(app.tools.some((tool) => tool.name === name));
    assert.ok(name.startsWith("history."));
    calls.push({name, args});
    if (unavailable) throw Error("CopyQ history service unavailable");
    return {entries:[{identity:id, preview, copied_at:null}]};
  },
};
const ClawUi = {
  node: (tag, text, attrs) => { const element = new Element(tag); if (text != null) element.textContent = String(text); for (const [k,v] of Object.entries(attrs || {})) element.setAttribute(k,v); return element; },
  showApp: () => {},
  replace: (target, children) => target.replaceChildren(...children),
  output: (target, value) => { target.textContent = JSON.stringify(value); },
  run: async (control, action, result, notice) => {
    control.disabled = true;
    try { const value = await action(); await result(value); return value; }
    catch (error) { notice.textContent = error.message; }
    finally { control.disabled = false; }
  },
  command: (owner, name, defaults, result, options) => {
    assert.equal(owner, app);
    assert.ok(ClawApp.tool(owner, name));
    reviews.push({name, defaults, result, options});
  },
};
vm.runInNewContext(fs.readFileSync(process.argv[1], "utf8"), {
  ClawApp, ClawUi, document:{getElementById:(name) => nodes[name]}, console,
});
const flush = () => new Promise((resolve) => setImmediate(resolve));
(async () => {
  await flush();
  assert.equal(calls.length, 0, "page load must not read history");
  assert.equal(nodes["selection-workspace"].hidden, true);
  nodes["history-load"].onclick({currentTarget:nodes["history-load"]}); await flush();
  assert.deepEqual(calls.map((call) => call.name), ["history.list"]);
  const control = nodes["history-items"].children[0];
  assert.equal(control.textContent, "1. " + preview);
  control.onclick();
  assert.equal(nodes["history-preview"].textContent, preview);
  assert.equal(calls.length, 1, "selecting a loaded preview makes no additional read");
  assert.equal(nodes["history-restore"].disabled, false);
  nodes["history-restore"].onclick();
  assert.equal(reviews[0].name, "history.restore");
  assert.equal(reviews[0].defaults.identity, id);
  assert.equal(reviews[0].options.fields.identity.readOnly, true);
  assert.ok(reviews[0].options.description.includes("clipboard.write:selection"));
  nodes["history-remove"].onclick();
  assert.equal(reviews[1].name, "history.remove");
  nodes["history-clear"].onclick();
  assert.equal(reviews[2].name, "history.clear");
  assert.equal(reviews[2].defaults.confirm, undefined, "clear confirmation must not be preselected");
  assert.equal(calls.length, 1, "opening a review makes no mutation");
  nodes["history-hide"].onclick();
  assert.equal(nodes["history-preview"].textContent, "No history item selected.");
  assert.equal(calls.length, 1, "hiding local preview must not clear backend history");
  unavailable = true;
  nodes["history-load"].onclick({currentTarget:nodes["history-load"]}); await flush();
  assert.equal(nodes.notice.textContent, "CopyQ history service unavailable");
  assert.equal(nodes["history-restore"].disabled, true);
  app.tools = [];
  nodes["history-load"].onclick({currentTarget:nodes["history-load"]}); await flush();
  assert.equal(calls.length, 2, "undeclared tools must never be dispatched");
})().catch((error) => { console.error(error); process.exitCode = 1; });
"""
    web = APP.parents[1] / "web"
    result = subprocess.run(
        [node, "-e", script, str(web / "app.js"), str(web / "index.html"), str(APP / "app.json")],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
