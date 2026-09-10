"""Real native stdio executable with synthetic commands and isolated OS brokers."""

import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from platform_dependency import prepare_exports
from stage import IGNORE, stage, stage_shared


def main():
    fixture = ROOT / "build/terminal-process-fixture"
    fixture.mkdir()
    process = None
    try:
        installed = fixture / "installed"
        stage("terminal", installed, ["cosmic-term"])
        libraries = prepare_exports(download=False)
        python = stage_shared(installed)
        shutil.copytree(libraries["python-sdk"] / "claw_os_sdk", python / "claw_os_sdk", ignore=IGNORE)
        shutil.copytree(libraries["python-runtime"] / "cos_runtime", python / "cos_runtime", ignore=IGNORE)
        namespace = "/run/terminal-fixture"
        (fixture / "owner").mkdir()
        (fixture / "work").mkdir()
        broker = fixture / "cos"
        broker.write_text(
            "#!/usr/bin/python3\n"
            "import json,pathlib,sys,os\n"
            f"root=pathlib.Path({namespace!r})\n"
            "args=sys.argv[1:]\n"
            "with (root/'calls').open('a') as f:f.write(json.dumps([args,os.environ.get('COS_SESSION')])+'\\n')\n"
            "if (root/'deny').exists():\n"
            " print(json.dumps({'wire_version':1,'ok':False,'error':{'code':'denied','message':'fixture denied'}}));sys.exit(1)\n"
            "if args[1]=='__policy':data={'decision':'allow','verb':args[3]}\n"
            "elif args[1]=='__desktop':data={'launched':True,'app_id':'com.clawos.Term','launcher':'/usr/bin/cosmic-term'}\n"
            "else:raise SystemExit(99)\n"
            "if (root/'wrong-target').exists():data['app_id']='com.clawos.Edit'\n"
            "print(json.dumps({'wire_version':1,'ok':True,'data':data}))\n"
        )
        broker.chmod(0o755)
        child = fixture / "fixture-command"
        child.write_text(
            "#!/usr/bin/python3\n"
            "import json,os,sys,time\n"
            "assert 'OPENAI_API_KEY' not in os.environ\n"
            "if sys.argv[1:] == ['timeout']: time.sleep(3)\n"
            "print(json.dumps(sys.argv[1:]))\n"
            "print('fixture stderr',file=sys.stderr)\n"
            "sys.exit(7 if sys.argv[1:] == ['failure'] else 0)\n"
        )
        child.chmod(0o755)
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
            "--ro-bind", str(child), "/usr/bin/fixture-command",
            "--setenv", "COS_MCP_SERVER", "1",
            "--setenv", "COS_APP_MANIFEST", "/usr/lib/cos/apps/cosmic-term/app.json",
            "--setenv", "COS_DATA_DIR", namespace + "/data",
            "--setenv", "COS_SESSION", "worker-session",
            "--setenv", "HOME", namespace + "/owner",
            "--setenv", "TMPDIR", namespace,
            "--setenv", "CLAW_COS_BIN", "/usr/local/bin/cos",
            "--setenv", "COS_BIN", "/untrusted/must-not-execute",
            "--setenv", "OPENAI_API_KEY", "synthetic-must-be-scrubbed",
            "--setenv", "PATH", "/usr/bin",
            "--setenv", "DISPLAY", "", "--setenv", "WAYLAND_DISPLAY", "",
            "--", str(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else
                       ROOT / "build/native-target/debug/cosmic-term"),
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
            assert selector.select(30), f"Terminal MCP timed out: {method}"
            line = process.stdout.readline()
            assert line, process.stderr.read()
            response = json.loads(line)
            assert response["id"] == counter
            return response

        def call(name, arguments, **context):
            return request("tools/call", {
                "name": f"term.{name}", "arguments": arguments,
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
            "clientInfo": {"name": "terminal-fixture", "version": "1"},
        })
        process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        process.stdin.flush()
        assert len(request("tools/list", {})["result"]["tools"]) == 3
        assert "error" in request("tools/call", {
            "name": "term.run", "arguments": {"command": "fixture-command"},
        })
        assert not (fixture / "calls").exists()
        result = success(call("run", {
            "command": "fixture-command", "arguments": ["--shell", "$(not-executed)", "a #é"],
        }))
        assert json.loads(result["stdout"]) == ["--shell", "$(not-executed)", "a #é"]
        assert result["stderr"] == "fixture stderr\n"
        assert result["exit_code"] == 0 and result["timed_out"] is False
        assert success(call("run", {"command": "fixture-command", "arguments": ["failure"]}))["exit_code"] == 7
        assert success(call("run", {
            "command": "fixture-command", "arguments": ["timeout"], "timeout_secs": 1,
        }))["timed_out"]
        assert call("run", {"command": "fixture-missing"})["result"]["isError"]
        assert success(call("which", {"program": "fixture-command"}))["path"] == "/usr/bin/fixture-command"
        assert success(call("which", {"program": "fixture-missing"})) == {
            "program": "fixture-missing", "path": None, "found": False,
        }
        assert success(call("open", {}))["opened"]
        assert success(call("open", {"cwd": namespace + "/work/a #é"}))["opened"]
        before = (fixture / "calls").read_bytes()
        for name, args, context in [
            ("run", {"command": ""}, {}), ("run", {"command": "fixture-command", "arguments": [1]}, {}),
            ("which", {"program": ""}, {}), ("open", {"cwd": 42}, {}),
            ("open", {"cwd": "relative"}, {}), ("run", {"command": "fixture-command"}, {"deadline_unix_ms": 1}),
        ]:
            response = call(name, args, **context)
            assert "error" in response or response["result"].get("isError"), response
        assert (fixture / "calls").read_bytes() == before
        (fixture / "deny").touch()
        for name, arguments in [
            ("run", {"command": "fixture-command"}), ("which", {"program": "fixture-command"}), ("open", {}),
        ]:
            assert call(name, arguments)["result"]["isError"]
        (fixture / "deny").unlink()
        (fixture / "wrong-target").touch()
        assert call("open", {})["result"]["isError"]
        calls = [json.loads(line) for line in (fixture / "calls").read_text().splitlines()]
        assert all("app" not in args and session == "worker-session" for args, session in calls)
        assert any("file:///run/terminal-fixture/work/a%20%23%C3%A9" in args for args, _ in calls)
        assert any(args[1:] == ["__policy", "check", "proc.spawn", "--name", "fixture-command"] for args, _ in calls)
        assert not (fixture / "data/proc").exists()
        print("Terminal binary: three authenticated tools, command/PATH/launch success, timeout, denial, expiry, no App intercall or session substitution passed")
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
