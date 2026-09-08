"""Exercise the real Editor stdio binary against fixture-only OS services."""

import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from stage import stage  # noqa: E402


def main():
    fixture = ROOT / "build/editor-process-fixture"
    fixture.mkdir()
    process = None
    try:
        stage("editor", fixture / "installed")
        broker = fixture / "cos"
        broker.write_text(
            "#!/usr/bin/python3\n"
            "import json, pathlib, sys\n"
            "root = pathlib.Path(__file__).parent\n"
            "args = sys.argv[1:]\n"
            "with (root / 'calls').open('a') as f: f.write(json.dumps(args) + '\\n')\n"
            "if (root / 'deny').exists():\n"
            " print(json.dumps({'ok':False,'wire_version':1,'error':{'code':'denied','message':'fixture denied'}})); sys.exit(1)\n"
            "if args[1] == '__filesystem':\n"
            " request = json.load(sys.stdin)\n"
            " with (root / 'requests').open('a') as f: f.write(json.dumps(request) + '\\n')\n"
            " if request['action'] == 'read': data = {'path':request['path'],'content':'untrusted document'}\n"
            " elif request['action'] == 'write': data = {'path':request['path'],'bytes':len(request['content'].encode())}\n"
            " else: data = {'replacements':1}\n"
            "elif args[1] == '__desktop':\n"
            " data = {'launched':True,'app_id':'com.clawos.Edit','launcher':'/usr/bin/gtk4-launch'}\n"
            "elif args[1] == 'ai':\n"
            " prompt = pathlib.Path(args[args.index('--prompt-file')+1]).read_text()\n"
            " with (root / 'prompts').open('a') as f: f.write(prompt + '\\n')\n"
            " data = {'text':'proposal','model':'fixture','provider':'fixture','verb':'ai.chat.untrusted',\n"
            " 'usage':{'input_tokens':1,'output_tokens':1,'units':1},\n"
            " 'budget':{'period':'fixture','units_used':1,'units_cap':200000},\n"
            " 'review':{'safety':'strict','prompt_redacted':False}}\n"
            "else: raise SystemExit(99)\n"
            "print(json.dumps({'ok':True,'wire_version':1,'data':data}))\n"
        )
        broker.chmod(0o755)
        env = {
            **os.environ, "COS_MCP_SERVER": "1",
            "COS_APP_MANIFEST": str(fixture / "installed/usr/lib/cos/apps/cosmic-edit/app.json"),
            "CLAW_COS_BIN": str(broker), "TMPDIR": str(fixture),
            "XDG_CONFIG_HOME": str(fixture / "config"),
            "XDG_DATA_HOME": str(fixture / "data"),
            "DISPLAY": "", "WAYLAND_DISPLAY": "",
        }
        process = subprocess.Popen(
            [str(ROOT / "build/native-target/debug/cosmic-edit")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env, cwd=fixture,
        )
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        counter = 0

        def request(method, params):
            nonlocal counter
            counter += 1
            process.stdin.write(json.dumps({
                "jsonrpc": "2.0", "id": counter, "method": method, "params": params,
            }) + "\n")
            process.stdin.flush()
            assert selector.select(15), f"Editor MCP timed out: {method}"
            line = process.stdout.readline()
            if not line:
                raise AssertionError(process.stderr.read())
            response = json.loads(line)
            assert response["id"] == counter
            return response

        def call(name, arguments, **context):
            return request("tools/call", {
                "name": f"edit.{name}", "arguments": arguments,
                "_meta": {"claw-os.dev/call-context": {
                    "wire_version": 1, "call_id": f"fixture-{counter}",
                    "trace_id": "fixture", "session_id": "fixture", "task_id": "fixture-task",
                    "caller": {"kind": "system-agent", "id": "fixture", "owner_uid": 1000},
                    **context,
                }},
            })

        def success(response):
            assert "error" not in response and not response["result"].get("isError"), response
            return json.loads(response["result"]["content"][0]["text"])

        assert "result" in request("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "editor-fixture", "version": "1"},
        })
        process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        process.stdin.flush()
        assert len(request("tools/list", {})["result"]["tools"]) == 7
        assert "error" in request("tools/call", {
            "name": "edit.write", "arguments": {"path": "/work/document", "content": "bad"},
        })
        assert not (fixture / "calls").exists()
        path = "/work/document"
        assert success(call("read", {"path": path}))["content"] == "untrusted document"
        assert success(call("write", {"path": path, "content": ""}))["written"]
        assert success(call("replace_range", {
            "path": path, "find": "document", "replace": "proposal",
        }))["replacements"] == 1
        assert success(call("open", {"path": "/work/a #é.txt"}))["opened"]
        assert success(call("open", {}))["opened"]
        for tool in ("summarize", "explain", "rewrite"):
            arguments = {"path": path}
            if tool == "rewrite":
                arguments["instruction"] = "make concise"
            success(call(tool, arguments))
        before = (fixture / "calls").read_bytes()
        for response in (
            call("write", {"path": path, "content": "expired"}, deadline_unix_ms=1),
            call("replace_range", {"path": path, "find": "", "replace": "bad"}),
            call("open", {"path": 42}),
        ):
            assert "error" in response or response["result"].get("isError"), response
        assert (fixture / "calls").read_bytes() == before
        (fixture / "deny").touch()
        for tool, arguments in (
            ("read", {"path": path}), ("write", {"path": path, "content": "bad"}),
            ("replace_range", {"path": path, "find": "document", "replace": "bad"}),
            ("open", {}), ("summarize", {"path": path}),
        ):
            assert call(tool, arguments)["result"]["isError"]
        calls = [json.loads(line) for line in (fixture / "calls").read_text().splitlines()]
        assert all("app" not in args for args in calls)
        ai = [args for args in calls if args[1] == "ai"]
        assert len(ai) == 3
        assert all(args[args.index("--app") + 1] == "cosmic-edit" for args in ai)
        assert all(args[args.index("--origin") + 1] == "external-content" for args in ai)
        assert any("file:///work/a%20%23%C3%A9.txt" in args for args in calls)
        prompts = [json.loads(line) for line in (fixture / "prompts").read_text().splitlines()]
        assert all(prompt["document"] == "untrusted document" for prompt in prompts)
        requests = [json.loads(line) for line in (fixture / "requests").read_text().splitlines()]
        assert sum(request["action"] in ("write", "replace") for request in requests) == 2
        print("Editor binary: authenticated seven tools, expiry, service denial, fixed launch and AI identity passed")
    finally:
        if process is not None:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
        shutil.rmtree(fixture)


if __name__ == "__main__":
    main()
