"""Real Capture binary/resources and published SDK clients over an isolated fake OS wire."""

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
    process = None
    try:
        installed = fixture / "installed"
        stage("capture", installed)
        native = options.source.resolve()
        installer = [
            "just", "--justfile", str(native / "justfile"), f"rootdir={installed}",
            "prefix=/usr", f"bin-src={options.binary.resolve()}", "install",
        ]
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
        output = fixture / "shots"
        output.mkdir()
        destination = output / "Screenshot_fixture.png"
        source = fixture / "human choice.png"
        source.write_bytes(PNG)
        (fixture / "image.png").write_bytes(PNG)
        for permission in ("screen", "write", "notify"):
            (fixture / permission).touch()
        broker = fixture / "cos"
        broker.write_text(
            """#!/usr/bin/python3
import json, os, pathlib, sys
root = pathlib.Path(__file__).parent
args = sys.argv[1:]
request = json.load(sys.stdin)
with (root / 'calls').open('a') as log:
    log.write(json.dumps({'args':args,'request':request,'app':os.environ.get('COS_APP_ID'),
        'session':os.environ.get('COS_SESSION'),'stderr_terminal':os.isatty(2)}) + '\\n')
def error(message):
    print(json.dumps({'ok':False,'wire_version':1,'code':'PERMISSION_DENIED','error':message}))
    sys.exit(1)
if not os.environ.get('COS_SESSION') and not os.isatty(2): error('no active session')
assert args[0] == '--wire=1'
if args[1] == '__capture':
    assert args[2:] == ['screenshot','--request-stdin']
    assert set(request) == {'directory','modal'}
    if not (root / 'screen').exists(): error('screen permission denied')
    if not (root / 'write').exists(): error('write permission denied')
    assert request['directory'] == str(root / 'shots')
    data = {'cancelled': (root / 'cancel').exists(), 'path': None}
    if not data['cancelled']:
        path = root / 'shots/Screenshot_fixture.png'
        try: fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError: error('output already exists')
        with os.fdopen(fd, 'wb') as image: image.write((root / 'image.png').read_bytes())
        data['path'] = str(path)
elif args[1] == '__gui-capture':
    assert args[3:] == ['--request-stdin']
    assert os.environ.get('COS_APP_GUI') == '1'
    assert os.environ.get('COS_SESSION')
    if not (root / 'screen').exists(): error('screen permission denied')
    invocation = request['request_id']
    assert len(invocation) == 32 and all(ch in '0123456789abcdef' for ch in invocation)
    held = root / 'held-gui.json'
    if args[2] == 'request':
        assert set(request) == {'request_id','modal'} and isinstance(request['modal'], bool)
        if held.exists(): assert json.loads(held.read_text()) == request
        else: held.write_text(json.dumps(request))
        data = {'version':1,'request_id':invocation,'status':'pending'}
    else:
        assert args[2] == 'status' and set(request) == {'request_id'}
        assert json.loads(held.read_text())['request_id'] == invocation
        data = {'version':1,'request_id':invocation,**json.loads((root / 'gui-reply.json').read_text())}
elif args[1] == '__notifications':
    assert args[2:5] == ['request','--request-stdin','--deadline'] and int(args[5]) > 0
    if not (root / 'notify').exists(): error('notification permission denied')
    assert request['action'] == 'post'
    assert set(request) == {'action','app_name','summary','body','icon','expire_ms','transient'}
    with (root / 'notifications').open('a') as log: log.write(json.dumps(request) + '\\n')
    data = {'id':'notif-' + 'a' * 32}
else:
    error('unsupported controlled primitive')
print(json.dumps({'ok':True,'wire_version':1,'data':data}))
"""
        )
        broker.chmod(0o755)
        env = {
            **os.environ,
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path={fixture}/no-user-bus",
            "DISPLAY": "", "WAYLAND_DISPLAY": "", "HOME": str(fixture / "home"),
            "XDG_CONFIG_HOME": str(fixture / "config"), "XDG_DATA_HOME": str(fixture / "data"),
            "TMPDIR": str(fixture), "COS_MCP_SERVER": "1", "COS_APP_ID": "cosmic-screenshot",
            "COS_SESSION": "broker-session",
            "COS_APP_MANIFEST": str(installed / "usr/lib/cos/apps/cosmic-screenshot/app.json"),
            "CLAW_COS_BIN": str(broker),
        }
        process = subprocess.Popen(
            [str(binary), "--portal-capture-stdout"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env=env, cwd=fixture,
        )
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
        assert tool["inputSchema"]["properties"]["interactive"]["enum"] == [False]
        assert "error" in request("tools/call", {
            "name": "screenshot.capture", "arguments": {"save_dir": str(output)},
        })
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
        assert success(call({"save_dir": str(output)})) == {"cancelled": False, "path": str(destination)}
        assert destination.read_bytes() == PNG and destination.stat().st_mode & 0o777 == 0o600
        destination.unlink()
        (fixture / "cancel").touch()
        assert success(call({"save_dir": str(output), "modal": False})) == {"cancelled": True, "path": None}
        assert not destination.exists()
        (fixture / "cancel").unlink()
        for permission in ("screen", "write"):
            (fixture / permission).unlink()
            assert call({"save_dir": str(output)})["result"]["isError"]
            (fixture / permission).touch()
        calls = [json.loads(value) for value in (fixture / "calls").read_text().splitlines()]
        assert all(value["args"][1] == "__capture" for value in calls)
        assert all(value["app"] == "cosmic-screenshot" and value["session"] == "broker-session" for value in calls)
        assert all(value["stderr_terminal"] is False for value in calls)

        human_env = {key: value for key, value in env.items() if key != "COS_MCP_SERVER"}
        human_env["COS_APP_GUI"] = "1"

        def human(reply, *args):
            (fixture / "held-gui.json").unlink(missing_ok=True)
            (fixture / "gui-reply.json").write_text(json.dumps(reply))
            return subprocess.run(
                [str(binary), "--gui", *args], env=human_env,
                capture_output=True, text=True, timeout=10,
            )

        for reply, expected in [({"status": "saved", "path": str(source)}, str(source)),
                                ({"status": "clipboard"}, "")]:
            result = human(reply, "--notify=false", "--modal=false", "--save-dir", str(output))
            assert result.returncode == 0 and result.stdout.strip() == expected, result.stderr
            assert source.read_bytes() == PNG and not destination.exists()
        assert not (fixture / "notifications").exists()
        for reply, expected in [({"status": "saved", "path": str(source)}, str(source)),
                                ({"status": "clipboard"}, "")]:
            result = human(reply)
            assert result.returncode == 0 and result.stdout.strip() == expected, result.stderr
        notifications = [json.loads(value) for value in (fixture / "notifications").read_text().splitlines()]
        assert [value["body"] for value in notifications] == [str(source), ""]
        assert all(value["icon"] == "com.clawos.Screenshot" and value["app_name"] and value["summary"]
                   and value["expire_ms"] == 5000 and value["transient"] for value in notifications)
        result = human({"status": "cancelled"})
        assert result.returncode == 0 and result.stdout.strip() == "Screenshot cancelled by user"
        assert len((fixture / "notifications").read_text().splitlines()) == 2
        for reply in [{"status": "cleanup_pending"}, {"status": "failed", "error": "portal refused"},
                      {"status": "saved", "path": "relative"}, {"status": "clipboard", "approved": True}]:
            result = human(reply)
            assert result.returncode != 0 and result.stderr, result
        (fixture / "screen").unlink()
        assert human({"status": "clipboard"}).returncode != 0
        (fixture / "screen").touch()
        (fixture / "notify").unlink()
        result = human({"status": "clipboard"})
        assert result.returncode != 0 and "notification permission denied" in result.stderr
        (fixture / "notify").touch()
        result = subprocess.run(
            [str(binary), "--gui", "--interactive=false", "--notify=false", "--save-dir", str(output)],
            env=human_env, capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0 and result.stdout.strip() == str(destination), result.stderr
        destination.unlink()
        terminal_env = {key: value for key, value in human_env.items() if key not in ("COS_SESSION", "COS_APP_GUI")}
        args = [str(binary), "--interactive=false", "--notify=false", "--save-dir", str(output)]
        result = subprocess.run(args, env=terminal_env, capture_output=True, text=True, timeout=10)
        assert result.returncode != 0 and "no active session" in result.stderr
        master, terminal = pty.openpty()
        try:
            result = subprocess.run(args, env=terminal_env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=terminal, text=True, timeout=10)
            assert result.returncode == 0 and result.stdout.strip() == str(destination)
        finally:
            os.close(terminal)
            os.close(master)
        result = subprocess.run([str(binary), "--portal-capture-stdout"], env=human_env,
                                capture_output=True, text=True, timeout=10)
        assert result.returncode != 0 and not result.stdout and "OS-owned" in result.stderr
        gui_calls = [value for value in map(json.loads, (fixture / "calls").read_text().splitlines())
                     if value["args"][1] == "__gui-capture"]
        assert any(value["args"][2] == "status" for value in gui_calls)
        assert any(value["request"].get("modal") is False for value in gui_calls)
        assert all(value["session"] == "broker-session" for value in gui_calls)
        print("Capture: real installed binary/resources; published-SDK MCP/GUI/notification clients, "
              "metadata-only file/clipboard/cancel, errors and terminal compatibility passed without a user bus. "
              "Root portal/authority/lifetime and physical UI acceptance are separate OS gates.")
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
