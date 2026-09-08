"""Real Capture binaries, isolated fixture portal/broker and installed resources."""

import argparse
import base64
import json
import os
from pathlib import Path
import pty
import selectors
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from stage import stage  # noqa: E402

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jP1kAAAAASUVORK5CYII="
)


def line(process, timeout=15):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        assert selector.select(timeout), "Capture fixture timed out"
        result = process.stdout.readline()
        assert result, process.stderr.read()
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/native-target/debug/cosmic-screenshot")
    parser.add_argument("--source", type=Path, default=ROOT / "build/capture-native")
    options = parser.parse_args()
    fixture = ROOT / "build/capture-process-fixture"
    fixture.mkdir()
    processes = []
    try:
        installed = fixture / "installed"
        stage("capture", installed)
        binary = options.binary.resolve()
        native = options.source.resolve()
        installer = [
            "just", "--justfile", str(native / "justfile"), f"rootdir={installed}",
            "prefix=/usr", f"bin-src={binary}", "install",
        ]
        plan = subprocess.run(
            [installer[0], "--dry-run", *installer[1:]], check=True, capture_output=True, text=True,
        )
        assert str(installed / "usr/bin/cosmic-screenshot") in plan.stdout + plan.stderr
        assert str(installed / "usr/share/applications") in plan.stdout + plan.stderr
        subprocess.run(installer, check=True, capture_output=True, text=True)
        binary = installed / "usr/bin/cosmic-screenshot"
        assert os.access(binary, os.X_OK)
        for resource in (native / "resources").rglob("*"):
            if resource.is_file():
                relative = resource.relative_to(native / "resources")
                target = installed / "usr/share" / (
                    Path("applications") / relative if relative.suffix == ".desktop" else relative
                )
                assert target.read_bytes() == resource.read_bytes(), target
        address = f"unix:path={fixture}/bus"
        bus = subprocess.Popen([
            "dbus-daemon", "--session", "--nofork", "--nopidfile", "--nosyslog",
            f"--address={address}", "--print-address=1",
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        processes.append(bus)
        assert line(bus).startswith(address)
        env = {
            **os.environ, "DBUS_SESSION_BUS_ADDRESS": address, "DISPLAY": "", "WAYLAND_DISPLAY": "",
            "HOME": str(fixture / "home"), "XDG_CONFIG_HOME": str(fixture / "config"),
            "XDG_DATA_HOME": str(fixture / "data"), "TMPDIR": str(fixture),
        }
        portal = subprocess.Popen([
            str(ROOT / "build/native-target/debug/examples/capture-portal-fixture"), str(fixture),
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        processes.append(portal)
        assert line(portal).strip() == "ready"
        source = fixture / "portal.png"
        output = fixture / "shots"
        output.mkdir()
        destination = output / "Screenshot_fixture.png"

        def reply(code=0, uri=None, content=PNG, **extra):
            source.write_bytes(content)
            source.chmod(0o600)
            (fixture / "portal-reply.json").write_text(json.dumps({
                "code": code, "uri": uri or source.as_uri(), **extra,
            }))

        broker = fixture / "cos"
        broker.write_text(
            "#!/usr/bin/python3\n"
            "import json, os, pathlib, subprocess, sys\n"
            "root = pathlib.Path(__file__).parent\n"
            "args = sys.argv[1:]\n"
            "request = json.load(sys.stdin)\n"
            "with (root / 'calls').open('a') as f:\n"
            " f.write(json.dumps({'args':args,'request':request,'app':os.environ.get('COS_APP_ID'),"
            "'session':os.environ.get('COS_SESSION'),'stderr_terminal':os.isatty(2)}) + '\\n')\n"
            "assert args == ['--wire=1','__capture','screenshot','--request-stdin']\n"
            "assert set(request) == {'directory','modal'}\n"
            "def error(message):\n"
            " print(json.dumps({'ok':False,'wire_version':1,'code':'PERMISSION_DENIED','error':message})); sys.exit(1)\n"
            "if not os.environ.get('COS_SESSION') and not os.isatty(2): error('no active session')\n"
            "if not (root / 'screen').exists(): error('screen permission denied')\n"
            "if not (root / 'write').exists(): error('write permission denied')\n"
            "assert request['directory'] == str(root / 'shots')\n"
            "child_env = {k:v for k,v in os.environ.items() if k not in "
            "('COS_MCP_SERVER','COS_APP_MANIFEST','COS_APP_ID','COS_SESSION','CLAW_COS_BIN')}\n"
            "child = subprocess.run([str(root / 'installed/usr/bin/cosmic-screenshot'),"
            "'--portal-capture-stdout', '--modal=' + str(request['modal']).lower()],"
            "env=child_env, capture_output=True, timeout=10)\n"
            "if child.returncode: error(child.stderr.decode())\n"
            "data = {'cancelled':not bool(child.stdout),'path':None}\n"
            "if child.stdout:\n"
            " assert child.stdout.startswith(b'\\x89PNG\\r\\n\\x1a\\n')\n"
            " path = root / 'shots/Screenshot_fixture.png'\n"
            " try: fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)\n"
            " except FileExistsError: error('output already exists')\n"
            " with os.fdopen(fd, 'wb') as f: f.write(child.stdout)\n"
            " data['path'] = str(path)\n"
            "print(json.dumps({'ok':True,'wire_version':1,'data':data}))\n"
        )
        broker.chmod(0o755)
        for permission in ("screen", "write"):
            (fixture / permission).touch()
        env.update({
            "COS_MCP_SERVER": "1", "COS_APP_ID": "cosmic-screenshot", "COS_SESSION": "broker-session",
            "COS_APP_MANIFEST": str(installed / "usr/lib/cos/apps/cosmic-screenshot/app.json"),
            "CLAW_COS_BIN": str(broker),
        })
        process = subprocess.Popen(
            [str(binary), "--portal-capture-stdout"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env=env, cwd=fixture,
        )
        processes.append(process)
        counter = 0

        def request(method, params):
            nonlocal counter
            counter += 1
            process.stdin.write(json.dumps({
                "jsonrpc": "2.0", "id": counter, "method": method, "params": params,
            }) + "\n")
            process.stdin.flush()
            result = json.loads(line(process))
            assert result["id"] == counter
            return result

        def call(arguments, **context):
            return request("tools/call", {
                "name": "screenshot.capture", "arguments": arguments,
                "_meta": {"claw-os.dev/call-context": {
                    "wire_version": 1, "call_id": f"fixture-{counter}", "trace_id": "fixture",
                    "session_id": "context-is-not-broker-authority", "task_id": "fixture-task",
                    "caller": {"kind": "system-agent", "id": "fixture", "owner_uid": 1000},
                    **context,
                }},
            })

        def success(response):
            assert "error" not in response and not response["result"].get("isError"), response
            return json.loads(response["result"]["content"][0]["text"])

        request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "capture-fixture", "version": "1"}})
        process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        process.stdin.flush()
        tool, = request("tools/list", {})["result"]["tools"]
        assert tool["name"] == "screenshot.capture"
        assert tool["inputSchema"]["properties"]["interactive"]["enum"] == [False]
        assert "error" in request("tools/call", {
            "name": "screenshot.capture", "arguments": {"save_dir": str(output)},
        })
        assert not (fixture / "calls").exists()
        for arguments in [
            {"save_dir": str(output), "interactive": True},
            {"save_dir": str(output), "modal": "false"},
            {"save_dir": 1}, {"save_dir": ""}, {"save_dir": "relative"},
            {"save_dir": "~/Pictures"}, {"save_dir": str(output), "owner_uid": 0},
        ]:
            response = call(arguments)
            assert "error" in response or response["result"].get("isError"), response
        expired = call({"save_dir": str(output)}, deadline_unix_ms=1)
        assert "error" in expired or expired["result"].get("isError")
        assert not (fixture / "calls").exists()
        reply()
        assert success(call({"save_dir": str(output)})) == {"cancelled": False, "path": str(destination)}
        assert destination.read_bytes() == PNG and not source.exists()
        assert destination.stat().st_mode & 0o777 == 0o600
        destination.unlink()
        reply(code=1)
        assert success(call({"save_dir": str(output), "modal": False})) == {"cancelled": True, "path": None}
        assert not destination.exists()
        for permission in ("screen", "write"):
            before = (fixture / "portal-calls").read_bytes()
            (fixture / permission).unlink()
            denied = call({"save_dir": str(output)})["result"]
            assert denied["isError"]
            assert f"{permission} permission denied" in denied["content"][0]["text"]
            assert (fixture / "portal-calls").read_bytes() == before
            (fixture / permission).touch()
        for options in [
            {"fail": True}, {"uri": "clipboard:"}, {"uri": "https://example.invalid/image.png"},
            {"content": b"not PNG"},
        ]:
            reply(**options)
            assert call({"save_dir": str(output)})["result"]["isError"]
            assert not destination.exists()
        calls = [json.loads(value) for value in (fixture / "calls").read_text().splitlines()]
        assert all(value["app"] == "cosmic-screenshot" for value in calls)
        assert all(value["session"] == "broker-session" for value in calls)
        assert all(value["stderr_terminal"] is False for value in calls)
        assert all("app" not in value["args"] for value in calls)
        assert not (fixture / "notification-calls").exists()
        human_env = {k: v for k, v in env.items() if k not in ("COS_MCP_SERVER", "COS_APP_ID")}
        before = (fixture / "calls").read_bytes()
        for uri, expected in [(source.as_uri(), str(source)), ("clipboard:", "")]:
            reply(uri=uri)
            human = subprocess.run([str(binary), "--notify=false", "--modal=false"],
                                   env=human_env, capture_output=True, text=True, timeout=10)
            assert human.returncode == 0, human.stderr
            assert human.stdout.strip() == expected
            assert source.read_bytes() == PNG
        assert not (fixture / "notification-calls").exists()
        for uri, expected in [(source.as_uri(), str(source)), ("clipboard:", "")]:
            reply(uri=uri)
            human = subprocess.run([str(binary)], env=human_env,
                                   capture_output=True, text=True, timeout=10)
            assert human.returncode == 0, human.stderr
            assert human.stdout.strip() == expected
        notifications = [
            json.loads(value) for value in (fixture / "notification-calls").read_text().splitlines()
        ]
        assert [value["body"] for value in notifications] == [str(source), ""]
        assert all(value["app_icon"] == "com.clawos.Screenshot" for value in notifications)
        assert all(value["app_name"] and value["summary"] for value in notifications)
        assert all(value["transient"] is True and value["expire_timeout"] == 5000
                   and value["actions"] == [] and value["replaces_id"] == 0 for value in notifications)
        reply(code=1)
        human = subprocess.run([str(binary)], env=human_env,
                               capture_output=True, text=True, timeout=10)
        assert human.returncode == 0 and human.stdout.strip() == "Screenshot cancelled by user"
        assert len((fixture / "notification-calls").read_text().splitlines()) == 2
        assert (fixture / "calls").read_bytes() == before
        reply()
        human = subprocess.run([
            str(binary), "--interactive=false", "--notify=false", "--save-dir", str(output),
        ], env=human_env, capture_output=True, text=True, timeout=10)
        assert human.returncode == 0, human.stderr
        assert human.stdout.strip() == str(destination) and destination.read_bytes() == PNG
        destination.unlink()
        reply()
        terminal_env = {k: v for k, v in human_env.items() if k != "COS_SESSION"}
        before = (fixture / "portal-calls").read_bytes()
        headless = subprocess.run([
            str(binary), "--interactive=false", "--notify=false", "--save-dir", str(output),
        ], env=terminal_env, capture_output=True, text=True, timeout=10)
        assert headless.returncode != 0 and "no active session" in headless.stderr
        assert (fixture / "portal-calls").read_bytes() == before
        assert not destination.exists()
        master, terminal = pty.openpty()
        try:
            human = subprocess.run([
                str(binary), "--interactive=false", "--notify=false", "--save-dir", str(output),
            ], env=terminal_env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=terminal,
                text=True, timeout=10)
            assert human.returncode == 0
            assert human.stdout.strip() == str(destination) and destination.read_bytes() == PNG
        finally:
            os.close(terminal)
            os.close(master)
        last_call = json.loads((fixture / "calls").read_text().splitlines()[-1])
        assert last_call["session"] is None and last_call["stderr_terminal"] is True
        portal_calls = [json.loads(value) for value in (fixture / "portal-calls").read_text().splitlines()]
        assert any(value["interactive"] is True and value["modal"] is False for value in portal_calls)
        assert any(value["interactive"] is False and value["modal"] is True for value in portal_calls)
        wrong = json.loads(Path(env["COS_APP_MANIFEST"]).read_text())
        wrong["id"] = "wrong-identity"
        (fixture / "wrong.json").write_text(json.dumps(wrong))
        failure = subprocess.run([str(binary)], env={**env, "COS_APP_MANIFEST": str(fixture / "wrong.json")},
                                 input="", capture_output=True, text=True, timeout=10)
        assert failure.returncode != 0 and "cosmic-screenshot identity" in failure.stderr
        print("Capture: installed binary/8 icons/desktop entry; authenticated MCP, exact SDK routing, "
              "fixture portal PNG/cancel/errors, human UI/notifications/terminal and unchanged identity passed")
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
        shutil.rmtree(fixture)


if __name__ == "__main__":
    main()
