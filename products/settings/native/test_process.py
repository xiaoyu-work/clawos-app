"""Exercise installed Settings resources and authenticated MCP without a desktop."""

import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from stage import stage


def main():
    fixture = ROOT / "build/settings-process-fixture"
    fixture.mkdir()
    process = None
    try:
        installed = fixture / "installed"
        stage("settings", installed, ["cosmic-settings"])
        subprocess.run([
            "just", "--justfile", str(ROOT / "build/settings-native/justfile"),
            f"rootdir={installed}", f"bin-src={ROOT / 'build/native-target/debug/cosmic-settings'}",
            "install",
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        binary = installed / "usr/bin/cosmic-settings"
        assert binary.stat().st_mode & 0o777 == 0o755
        resources = installed / "usr/share"
        desktop = resources / "applications/com.clawos.Settings.desktop"
        assert "Exec=cosmic-settings" in desktop.read_text()
        assert "Name[fr]=" in desktop.read_text()
        entries = list((resources / "applications").glob("com.clawos.Settings*.desktop"))
        assert len(entries) == 32
        schemas = ROOT / "build/settings-native/resources/default_schema"
        for source in schemas.rglob("*"):
            if source.is_file():
                assert (resources / "cosmic" / source.relative_to(schemas)).read_bytes() == source.read_bytes()
        for relative in (
            "metainfo/com.clawos.Settings.metainfo.xml",
            "icons/hicolor/scalable/apps/com.clawos.Settings.svg",
            "polkit-1/actions/com.clawos.Settings.Users.policy",
            "polkit-1/rules.d/cosmic-settings.rules",
        ):
            assert (resources / relative).is_file(), relative
        namespace = "/run/settings-fixture"
        broker = fixture / "cos"
        broker.write_text(
            "#!/usr/bin/python3\n"
            "import json,pathlib,sys,os\n"
            f"root=pathlib.Path({namespace!r})\n"
            "args=sys.argv[1:]\n"
            "with (root/'calls').open('a') as f:f.write(json.dumps([args,os.environ.get('COS_SESSION')])+'\\n')\n"
            "if args[1]=='__app-permissions':\n"
            " request=json.loads(args[2]);assert not {'owner_uid','session','confirm','approve'} & request.keys()\n"
            " action=request['action'];assert action in ['list','show','request','revoke']\n"
            " if (root/'deny').exists():\n"
            "  print(json.dumps({'wire_version':1,'ok':False,'error':{'code':'denied','message':'permission fixture denied'}}));sys.exit(1)\n"
            " data={'list':{'apps':[{'app_id':'audio-manager'}]},'show':{'app_id':'audio-manager','permissions':[{'permission_id':'exact-id','enabled':False,'live_granted':False}]},'request':{'id':'ap-fixture','status':'pending','enabled':False},'revoke':{'revoked':True,'enabled':False,'restart_required':True}}[action]\n"
            " print(json.dumps({'wire_version':1,'ok':True,'data':data}));sys.exit(0)\n"
            "assert args[1:5]==['__desktop','launch','--app-id','com.clawos.Settings'],args\n"
            "assert args[5:] in ([],['--uri','settings://wireless'],['--uri','settings://accessibility-magnifier'],['--uri','settings://dock-applet'],['--uri','settings://panel-applet']),args\n"
            "if (root/'deny').exists():\n"
            " print(json.dumps({'wire_version':1,'ok':False,'error':{'code':'denied','message':'fixture denied'}}));sys.exit(1)\n"
            "data={'launched':True,'app_id':'com.clawos.Settings','launcher':'/usr/bin/cosmic-settings'}\n"
            "if (root/'wrong-target').exists():data['app_id']='com.clawos.Store'\n"
            "print(json.dumps({'wire_version':1,'ok':True,'data':data}))\n"
        )
        broker.chmod(0o755)
        command = [
            "bwrap", "--die-with-parent", "--unshare-net", "--ro-bind", "/", "/",
            "--dev", "/dev", "--tmpfs", "/run", "--tmpfs", "/usr/local/bin", "--tmpfs", "/usr/bin",
            "--bind", str(fixture), namespace,
            "--ro-bind", str(Path("/usr/bin/python3").resolve()), "/usr/bin/python3",
            "--ro-bind", str(broker), "/usr/local/bin/cos",
            "--ro-bind", str(binary), "/usr/bin/cosmic-settings",
            "--chdir", namespace,
        ]
        for name, value in {
            "COS_MCP_SERVER": "1",
            "COS_APP_MANIFEST": namespace + "/installed/usr/lib/cos/apps/cosmic-settings/app.json",
            "COS_SESSION": "worker-session", "COS_DATA_DIR": namespace + "/data",
            "HOME": namespace, "XDG_CONFIG_HOME": namespace + "/config",
            "XDG_DATA_HOME": namespace + "/data", "XDG_CACHE_HOME": namespace + "/cache",
            "XDG_RUNTIME_DIR": namespace, "TMPDIR": namespace,
            "CLAW_COS_BIN": "/usr/local/bin/cos", "PATH": "/usr/bin",
            "DISPLAY": "", "WAYLAND_DISPLAY": "", "DBUS_SESSION_BUS_ADDRESS": "",
            "DBUS_SYSTEM_BUS_ADDRESS": "unix:path=/not-present",
        }.items():
            command += ["--setenv", name, value]
        process = subprocess.Popen(
            [*command, "--", "/usr/bin/cosmic-settings"],
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
            assert selector.select(30), f"Settings MCP timed out: {method}"
            line = process.stdout.readline()
            assert line, process.stderr.read()
            response = json.loads(line)
            assert response["id"] == counter
            return response

        def call(name, args, **context):
            return request("tools/call", {
                "name": "settings." + name, "arguments": args,
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
                              "clientInfo": {"name": "settings-fixture", "version": "1"}})
        process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        process.stdin.flush()
        assert {tool["name"] for tool in request("tools/list", {})["result"]["tools"]} == {
            "settings.list_pages", "settings.search", "settings.open",
            "settings.permissions_list", "settings.permissions_show",
            "settings.permissions_request", "settings.permissions_revoke",
        }
        assert "error" in request("tools/call", {"name": "settings.list_pages", "arguments": {}})
        pages = success(call("list_pages", {}))["pages"]
        assert len(pages) == 31 and len({page["id"] for page in pages}) == 31
        assert success(call("search", {"query": "WI-FI"}))["hits"][0]["id"] == "wireless"
        assert len(success(call("search", {"query": ""}))["hits"]) == 5
        assert len(success(call("search", {"query": "", "limit": 0}))["hits"]) == 1
        assert len(success(call("search", {"query": "", "limit": 100}))["hits"]) == 20
        assert not (fixture / "calls").exists()
        assert success(call("open", {}))["opened"]
        assert success(call("open", {"page": "wireless"}))["opened"]
        for page in ["accessibility-magnifier", "dock-applet", "panel-applet"]:
            assert success(call("open", {"page": page}))["opened"]
        before = (fixture / "calls").read_bytes()
        for name, args, context in [
            ("open", {"page": "--help"}, {}), ("open", {"page": "missing-page"}, {}),
            ("open", {"page": "../users"}, {}), ("open", {"page": 1}, {}),
            ("search", {}, {}), ("search", {"query": 1}, {}),
            ("search", {"query": "wireless", "limit": "1"}, {}),
            ("open", {}, {"deadline_unix_ms": 1}), ("set_volume", {}, {}),
        ]:
            reply = call(name, args, **context)
            assert "error" in reply or reply["result"].get("isError"), reply
        assert (fixture / "calls").read_bytes() == before
        assert success(call("permissions_list", {}))["apps"][0]["app_id"] == "audio-manager"
        assert not success(call("permissions_show", {"app_id": "audio-manager"}))["permissions"][0]["enabled"]
        pending = success(call("permissions_request", {
            "app_id": "audio-manager", "permission_id": "exact-id", "reason": "Need audio status",
        }))
        assert pending["status"] == "pending" and pending["enabled"] is False
        assert success(call("permissions_revoke", {
            "app_id": "audio-manager", "permission_id": "exact-id",
        }))["revoked"]
        before = (fixture / "calls").read_bytes()
        for name, args in [
            ("permissions_approve", {"id": "ap-fixture", "confirm": True}),
            ("permissions_request", {"app_id": "audio-manager", "permission_id": "exact-id",
                                     "reason": "forged", "owner_uid": 0}),
            ("permissions_show", {"app_id": "audio-manager", "session": "another-owner"}),
            ("permissions_revoke", {"app_id": "audio-manager"}),
        ]:
            reply = call(name, args)
            assert "error" in reply or reply["result"].get("isError"), reply
        assert (fixture / "calls").read_bytes() == before
        (fixture / "deny").touch()
        assert call("open", {})["result"]["isError"]
        assert call("permissions_list", {})["result"]["isError"]
        (fixture / "deny").unlink()
        (fixture / "wrong-target").touch()
        assert call("open", {})["result"]["isError"]
        calls = [json.loads(line) for line in (fixture / "calls").read_text().splitlines()]
        assert all(sid == "worker-session" and "app" not in args for args, sid in calls)
        assert not (fixture / "config").exists()
        print("Settings installed binary/resources: 32 localized entries, schemas/polkit/icons; "
              "seven authenticated MCP tools, owner/session injection and self-approval rejection, "
              "pending restoration and revocation responses; 31 pages, search clamps, fixed launch, denial, "
              "expiry and wrong-target rejection; no GUI/device/account access")
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
