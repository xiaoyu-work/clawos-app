"""Real Files stdio executable, synthetic files and isolated fake OS services."""

import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from platform_dependency import prepare  # noqa: E402
from stage import stage  # noqa: E402


def main():
    fixture = ROOT / "build/files-process-fixture"
    fixture.mkdir()
    process = None
    try:
        installed = fixture / "installed"
        stage("files", installed, ["cosmic-files"])
        libraries = prepare()
        python = installed / "usr/lib/cos/python"
        python.mkdir(parents=True)
        shutil.copytree(libraries[0] / "claw_os_sdk", python / "claw_os_sdk")
        shutil.copytree(libraries[1] / "cos_runtime", python / "cos_runtime")
        shutil.copytree(libraries[2] / "_shared", installed / "usr/lib/cos/apps/_shared")
        namespace = "/run/files-fixture"
        (fixture / "owner/.recoll/xapiandb").mkdir(parents=True)
        (fixture / "work").mkdir()
        (fixture / "work/a.txt").write_text("untrusted document")
        (fixture / "work/.cos-meta.json").write_text('{"a.txt":{"tags":["fixture"]}}')
        (fixture / "work/link.txt").symlink_to("a.txt")
        broker = fixture / "cos"
        broker.write_text(
            "#!/usr/bin/python3\n"
            "import json,pathlib,sys\n"
            f"root=pathlib.Path({namespace!r})\n"
            "args=sys.argv[1:]\n"
            "with (root/'calls').open('a') as f: f.write(json.dumps(args)+'\\n')\n"
            "if (root/'deny').exists():\n"
            " print(json.dumps({'wire_version':1,'ok':False,'error':{'code':'denied','message':'fixture denied'}}));sys.exit(1)\n"
            "if args[1]=='__policy': data={'decision':'allow','verb':args[3]}\n"
            "elif args[1]=='__desktop':\n"
            f" data={{'launched':True,'app_id':'com.clawos.Files','launcher':'/usr/bin/gtk4-launch','directory':{namespace + '/work'!r}}}\n"
            "elif args[1]=='ai':\n"
            " prompt=pathlib.Path(args[args.index('--prompt-file')+1]).read_text()\n"
            " with (root/'prompts').open('a') as f:f.write(prompt+'\\n')\n"
            " data={'text':'proposal','model':'fixture','provider':'fixture','verb':'ai.chat.untrusted',\n"
            " 'usage':{'input_tokens':1,'output_tokens':1,'units':1},\n"
            " 'budget':{'period':'fixture','units_used':1,'units_cap':200000},\n"
            " 'review':{'safety':'strict','prompt_redacted':False}}\n"
            " if (root/'model-tools').exists():data['tool_calls']=[{'id':'bad','name':'other-app','input':{}}]\n"
            "elif '__memory' in args:\n"
            " payload=json.loads(args[args.index('--json')+1])\n"
            " with (root/'memory').open('a') as f:f.write(json.dumps(payload)+'\\n')\n"
            " data={'ok':True}\n"
            "else:raise SystemExit(99)\n"
            "print(json.dumps({'wire_version':1,'ok':True,'data':data}))\n"
        )
        broker.chmod(0o755)
        recoll = fixture / "recollq"
        recoll.write_text(
            "#!/usr/bin/python3\n"
            "import json,os,pathlib,sys\n"
            f"root=pathlib.Path({namespace!r})\n"
            "with (root/'recoll-calls').open('a') as f:f.write(json.dumps([sys.argv,os.environ['HOME']])+'\\n')\n"
            "if (root/'recoll-fail').exists():print('fixture failure',file=sys.stderr);sys.exit(3)\n"
            f"print('\\\"file://{namespace}/work/a.txt\\\" \\\"text/plain\\\" \\\"123\\\" \\\"fixture match\\\"')\n"
        )
        recoll.chmod(0o755)
        command = [
            "bwrap", "--die-with-parent", "--unshare-net", "--ro-bind", "/", "/",
            "--dev", "/dev", "--tmpfs", "/run", "--tmpfs", "/usr/lib",
            "--tmpfs", "/usr/local/bin", "--tmpfs", "/usr/bin",
        ]
        for library in Path("/usr/lib").iterdir():
            if library.name != "cos":
                command.extend(["--ro-bind", str(library), str(library)])
        command += [
            "--bind", str(fixture), namespace,
            "--ro-bind", str(Path("/usr/bin/python3").resolve()), "/usr/bin/python3",
            "--ro-bind", str(installed / "usr/lib/cos"), "/usr/lib/cos",
            "--ro-bind", str(broker), "/usr/local/bin/cos",
            "--ro-bind", str(recoll), "/usr/bin/recollq",
            "--setenv", "COS_MCP_SERVER", "1",
            "--setenv", "COS_APP_MANIFEST", "/usr/lib/cos/apps/cosmic-files/app.json",
            "--setenv", "COS_OWNER_HOME", namespace + "/owner",
            "--setenv", "COS_DATA_DIR", namespace + "/data",
            "--setenv", "TMPDIR", namespace,
            "--setenv", "CLAW_COS_BIN", "/usr/local/bin/cos",
            "--setenv", "COS_BIN", "/untrusted/must-not-execute",
            "--setenv", "DISPLAY", "", "--setenv", "WAYLAND_DISPLAY", "",
            "--", str(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else
                       ROOT / "build/native-target/debug/cosmic-files"),
        ]
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
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
            assert selector.select(30), f"Files MCP timed out: {method}"
            line = process.stdout.readline()
            assert line, process.stderr.read()
            response = json.loads(line)
            assert response["id"] == counter
            return response

        def call(name, arguments, **context):
            return request("tools/call", {
                "name": f"files.{name}", "arguments": arguments,
                "_meta": {"claw-os.dev/call-context": {
                    "wire_version": 1, "call_id": f"fixture-{counter}", "trace_id": "fixture",
                    "session_id": "caller-session", "task_id": "fixture-task",
                    "caller": {"kind": "system-agent", "id": "fixture", "owner_uid": 1000},
                    **context,
                }},
            })

        def success(reply):
            assert "error" not in reply and not reply["result"].get("isError"), reply
            return json.loads(reply["result"]["content"][0]["text"])

        request("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "files-fixture", "version": "1"},
        })
        process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        process.stdin.flush()
        assert len(request("tools/list", {})["result"]["tools"]) == 7
        assert "error" in request("tools/call", {
            "name": "files.list", "arguments": {"path": namespace + "/work"},
        })
        assert not (fixture / "calls").exists()
        path = namespace + "/work/a.txt"
        assert success(call("list", {"path": namespace + "/work"}))["entries"]
        assert success(call("metadata", {"path": path}))["tags"] == ["fixture"]
        assert success(call("search", {"root": namespace + "/work", "query": "a.txt"}))["matches"]
        assert success(call("reveal", {"path": path}))["opened"] == namespace + "/work"
        assert success(call("explain", {"path": path}))["text"] == "proposal"
        assert success(call("summarize", {"path": path}))["text"] == "proposal"
        assert success(call("find_similar", {"path": path}))["matches"][0]["snippet"] == "fixture match"
        before = (fixture / "calls").read_bytes()
        assert call("explain", {"path": path}, deadline_unix_ms=1)["result"]["isError"]
        assert call("explain", {"path": 42})["result"]["isError"]
        assert (fixture / "calls").read_bytes() == before
        assert call("explain", {"path": namespace + "/work/link.txt"})["result"]["isError"]
        (fixture / "deny").touch()
        for name, args in [
            ("list", {"path": namespace + "/work"}), ("metadata", {"path": path}),
            ("search", {"root": namespace + "/work", "query": "a"}),
            ("explain", {"path": path}), ("reveal", {"path": path}),
            ("find_similar", {"path": path}),
        ]:
            assert call(name, args)["result"]["isError"]
        (fixture / "deny").unlink()
        (fixture / "model-tools").touch()
        assert call("explain", {"path": path})["result"]["isError"]
        (fixture / "model-tools").unlink()
        (fixture / "recoll-fail").touch()
        assert call("find_similar", {"path": path})["result"]["isError"]
        calls = [json.loads(line) for line in (fixture / "calls").read_text().splitlines()]
        assert all("app" not in args for args in calls)
        ai_calls = [args for args in calls if "ai" in args]
        assert ai_calls and all(args[args.index("--app") + 1] == "cosmic-files" for args in ai_calls)
        assert all(args[args.index("--origin") + 1] == "external-content" for args in ai_calls)
        prompts = [json.loads(line) for line in (fixture / "prompts").read_text().splitlines()]
        assert all(prompt["document"] == "untrusted document" for prompt in prompts)
        recoll_calls = [json.loads(line) for line in (fixture / "recoll-calls").read_text().splitlines()]
        assert all(home == namespace + "/owner" for _, home in recoll_calls)
        memories = [json.loads(line) for line in (fixture / "memory").read_text().splitlines()]
        assert all(memory["source"] == "cosmic-files" for memory in memories)
        assert (fixture / "work/a.txt").read_text() == "untrusted document"
        print("Files binary: 7 authenticated tools, exact denials, AI identity, shared parser/Recoll passed")
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
