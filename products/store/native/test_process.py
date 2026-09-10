"""Run the installed Store binary against synthetic catalogs and an OS broker."""

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
    fixture = ROOT / "build/store-process-fixture"
    fixture.mkdir()
    process = None
    try:
        installed = fixture / "installed"
        stage("store", installed, ["cosmic-store"])
        libraries = prepare_exports(download=False)
        python = stage_shared(installed)
        shutil.copytree(libraries["python-sdk"] / "claw_os_sdk", python / "claw_os_sdk", ignore=IGNORE)
        shutil.copytree(libraries["python-runtime"] / "cos_runtime", python / "cos_runtime", ignore=IGNORE)
        subprocess.run([
            "just", "--justfile", str(ROOT / "build/store-native/justfile"),
            f"rootdir={installed}", f"bin-src={ROOT / 'build/native-target/debug/cosmic-store'}",
            "install",
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        binary = installed / "usr/bin/cosmic-store"
        assert binary.stat().st_mode & 0o777 == 0o755
        assert "Exec=cosmic-store" in (installed / "usr/share/applications/com.clawos.Store.desktop").read_text()
        assert (installed / "usr/share/metainfo/com.clawos.Store.metainfo.xml").is_file()
        assert (installed / "usr/share/icons/hicolor/scalable/apps/com.clawos.Store.svg").is_file()
        assert (ROOT / "build/native-target/debug/flathub-stats").is_file()
        namespace = "/run/store-fixture"
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
            "elif args[1]=='__desktop':data={'launched':True,'app_id':'com.clawos.Store','launcher':'/usr/bin/cosmic-store'}\n"
            "else:raise SystemExit(99)\n"
            "if (root/'wrong-target').exists():data['app_id']='com.clawos.Term'\n"
            "print(json.dumps({'wire_version':1,'ok':True,'data':data}))\n"
        )
        broker.chmod(0o755)
        for name in ("apt-cache", "dpkg"):
            child = fixture / name
            child.write_text(
                "#!/usr/bin/python3\n"
                "import json,pathlib,sys,os\n"
                f"root=pathlib.Path({namespace!r})\n"
                "assert 'OPENAI_API_KEY' not in os.environ\n"
                "with (root/'queries').open('a') as f:f.write(json.dumps(sys.argv)+'\\n')\n"
                "if (root/'query-error').exists(): print('synthetic catalog failure',file=sys.stderr);sys.exit(7)\n"
                "args=sys.argv[1:]\n"
                "if args == ['--get-selections']: print('fixture-one\\tinstall\\nfixture-two\\tinstall')\n"
                "elif args[:2] == ['search','--names-only']: print('fixture-one - First package\\nfixture-two - Second package')\n"
                "elif args == ['show','fixture-one']: print('Package: fixture-one\\nVersion: 1.2\\nDescription: First package\\n Long description\\nDepends: fixture-two')\n"
                "else:raise SystemExit(98)\n"
            )
            child.chmod(0o755)
        command = [
            "bwrap", "--die-with-parent", "--unshare-net", "--ro-bind", "/", "/",
            "--dev", "/dev", "--tmpfs", "/run", "--tmpfs", "/usr/lib",
            "--tmpfs", "/usr/local/bin", "--tmpfs", "/usr/bin",
        ]
        for library in Path("/usr/lib").iterdir():
            if library.name != "cos":
                command += ["--ro-bind", str(library), str(library)]
        command += [
            "--bind", str(fixture), namespace,
            "--ro-bind", str(Path("/usr/bin/python3").resolve()), "/usr/bin/python3",
            "--ro-bind", str(installed / "usr/lib/cos"), "/usr/lib/cos",
            "--ro-bind", str(broker), "/usr/local/bin/cos",
            "--ro-bind", str(binary), "/usr/bin/cosmic-store",
        ]
        for name in ("apt-cache", "dpkg"):
            command += ["--ro-bind", str(fixture / name), "/usr/bin/" + name]
        for name, value in {
            "COS_MCP_SERVER": "1", "COS_APP_MANIFEST": "/usr/lib/cos/apps/cosmic-store/app.json",
            "COS_SESSION": "worker-session", "COS_DATA_DIR": namespace + "/data",
            "HOME": namespace, "TMPDIR": namespace, "CLAW_COS_BIN": "/usr/local/bin/cos",
            "COS_BIN": "/untrusted/must-not-execute", "OPENAI_API_KEY": "synthetic-scrub-me",
            "PATH": "/usr/bin", "DISPLAY": "", "WAYLAND_DISPLAY": "",
        }.items():
            command += ["--setenv", name, value]
        process = subprocess.Popen(
            [*command, "--", "/usr/bin/cosmic-store"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
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
            assert selector.select(30), f"Store MCP timed out: {method}"
            line = process.stdout.readline()
            assert line, process.stderr.read()
            response = json.loads(line)
            assert response["id"] == counter
            return response

        def call(name, args, **context):
            return request("tools/call", {
                "name": "store." + name, "arguments": args,
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

        request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                              "clientInfo": {"name": "store-fixture", "version": "1"}})
        process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        process.stdin.flush()
        assert {tool["name"] for tool in request("tools/list", {})["result"]["tools"]} == {
            "store.search", "store.installed", "store.show", "store.open",
        }
        assert "error" in request("tools/call", {"name": "store.installed", "arguments": {}})
        assert not (fixture / "calls").exists()
        result = success(call("search", {"query": "--limit", "limit": 1}))
        assert result["count"] == 1 and result["truncated"] is True
        assert success(call("search", {"query": "fixture", "limit": -1}))["count"] == 1
        assert success(call("installed", {}))["packages"] == ["fixture-one", "fixture-two"]
        result = success(call("show", {"name": "fixture-one"}))
        assert result["version"] == "1.2" and result["description"] == "Long description"
        assert success(call("open", {}))["opened"]
        assert success(call("open", {"name": "fixture-one"}))["opened"]
        before = (fixture / "calls").read_bytes()
        for name, args, context in [
            ("search", {"query": ""}, {}), ("search", {"query": "fixture", "limit": "2"}, {}),
            ("show", {"name": "../escape"}, {}), ("open", {"name": "-oHook=id"}, {}),
            ("installed", {}, {"deadline_unix_ms": 1}),
            ("install", {"name": "fixture-one"}, {}),
        ]:
            reply = call(name, args, **context)
            assert "error" in reply or reply["result"].get("isError"), reply
        assert (fixture / "calls").read_bytes() == before
        (fixture / "query-error").touch()
        for name, args in [("search", {"query": "fixture"}), ("show", {"name": "fixture-one"}), ("installed", {})]:
            assert call(name, args)["result"]["isError"]
        (fixture / "query-error").unlink()
        before_queries = (fixture / "queries").read_bytes()
        (fixture / "deny").touch()
        for name, args in [("search", {"query": "fixture"}), ("show", {"name": "fixture-one"}), ("installed", {}), ("open", {})]:
            assert call(name, args)["result"]["isError"]
        assert (fixture / "queries").read_bytes() == before_queries
        (fixture / "deny").unlink()
        (fixture / "wrong-target").touch()
        assert call("open", {})["result"]["isError"]
        calls = [json.loads(line) for line in (fixture / "calls").read_text().splitlines()]
        assert all("app" not in args and "__package" not in args and sid == "worker-session" for args, sid in calls)
        assert any(args[1:] == ["__policy", "check", "sys.observe", "--name", "packages"] for args, _ in calls)
        assert any(args[1:] == ["__policy", "check", "sys.observe", "--name", "fixture-one"] for args, _ in calls)
        assert any("apt://fixture-one" in args for args, _ in calls)
        queries = [json.loads(line) for line in (fixture / "queries").read_text().splitlines()]
        assert queries[0][1:] == ["search", "--names-only", "--", "--limit"]
        print("Store installed binary: four authenticated tools; synthetic catalog/launch, errors, exact scopes, denial, expiry, no App dispatch or package transactions passed")
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
