"""Exercise installed Settings resources and authenticated MCP without a desktop."""

import argparse
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-root", type=Path, default=ROOT / "build/settings-native",
                        help="Explicit canonical prepared native source under build/")
    parser.add_argument("--target-dir", type=Path, default=ROOT / "build/native-target",
                        help="Cargo target containing the matching debug binary")
    options = parser.parse_args()
    build_root = options.build_root.resolve()
    target_dir = options.target_dir.resolve()
    for directory in (build_root, target_dir):
        if directory == ROOT / "build" or not directory.is_relative_to(ROOT / "build"):
            parser.error("Fixture build and target directories must be explicit paths under build/")
    if not (build_root / "Cargo.toml").is_file() or not (target_dir / "debug/cosmic-settings").is_file():
        parser.error("Build the prepared Settings candidate and its matching debug binary first")
    environment = {**os.environ, "CARGO_TARGET_DIR": str(target_dir)}
    fixture = ROOT / "build/settings-process-fixture"
    fixture.mkdir()
    process = None
    try:
        installed = fixture / "installed"
        stage("settings", installed, ["cosmic-settings"])
        subprocess.run([
            "just", "--justfile", str(build_root / "justfile"),
            f"rootdir={installed}", f"bin-src={target_dir / 'debug/cosmic-settings'}",
            "install",
        ], check=True, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        binary = installed / "usr/bin/cosmic-settings"
        assert binary.stat().st_mode & 0o777 == 0o755
        resources = installed / "usr/share"
        desktop = resources / "applications/com.clawos.Settings.desktop"
        assert "Exec=cosmic-settings" in desktop.read_text()
        assert "Name[fr]=" in desktop.read_text()
        entries = list((resources / "applications").glob("com.clawos.Settings*.desktop"))
        assert len(entries) == 32
        schemas = build_root / "resources/default_schema"
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
            "assert 'CLAW_COS_BIN' not in os.environ\n"
            "assert os.environ['PATH']=='/usr/sbin:/usr/bin:/sbin:/bin'\n"
            "args=sys.argv[1:]\n"
            "with (root/'calls').open('a') as f:f.write(json.dumps([args,os.environ.get('COS_SESSION')])+'\\n')\n"
            "if args[1]=='__app-permissions':\n"
            " request=json.loads(args[2]);assert not {'owner_uid','session','confirm','approve'} & request.keys()\n"
            " action=request['action'];assert action in ['list','show','request','revoke']\n"
            " if (root/'transport-failure').exists():\n"
            "  print('synthetic permission transport failure',file=sys.stderr);sys.exit(75)\n"
            " if (root/'deny').exists():\n"
            "  print(json.dumps({'wire_version':1,'ok':False,'code':'PERMISSION_DENIED','error':'permission fixture denied'}));sys.exit(1)\n"
            " data={'list':{'apps':[{'app_id':'audio-manager'}]},'show':{'app_id':'audio-manager','permissions':[{'permission_id':'exact-id','enabled':False,'live_granted':False}]},'request':{'id':'ap-fixture','status':'pending','enabled':False},'revoke':{'revoked':True,'enabled':False,'restart_required':True}}[action]\n"
            " if action=='show' and (root/'permission-state.json').exists():data=json.loads((root/'permission-state.json').read_text())\n"
            " print(json.dumps({'wire_version':1,'ok':True,'data':data}));sys.exit(0)\n"
            "assert args[1:5]==['__desktop','launch','--app-id','com.clawos.Settings'],args\n"
            "assert args[5:] in ([],['--uri','settings://wireless'],['--uri','settings://accessibility-magnifier'],['--uri','settings://dock-applet'],['--uri','settings://panel-applet']),args\n"
            "if (root/'deny').exists():\n"
            " print(json.dumps({'wire_version':1,'ok':False,'code':'PERMISSION_DENIED','error':'fixture denied'}));sys.exit(1)\n"
            "data={'launched':True,'app_id':'com.clawos.Settings','launcher':'/usr/bin/cosmic-settings'}\n"
            "if (root/'wrong-target').exists():data['app_id']='com.clawos.Store'\n"
            "print(json.dumps({'wire_version':1,'ok':True,'data':data}))\n"
        )
        broker.chmod(0o755)
        command = [
            "bwrap", "--die-with-parent", "--unshare-net", "--clearenv", "--ro-bind", "/", "/",
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
            "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
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

        def os_permission_state(enabled, *, pending=False, decision=None):
            value = {
                "app_id": "audio-manager", "trust": "verified",
                "permissions": [{
                    "permission_id": "exact-id", "declared": {"verb": "sys.observe"},
                    "capability": None, "manageable": True, "enabled": enabled,
                    "live_granted": False, "limitation": None,
                }],
                "pending": [{
                    "id": "ap-fixture", "verb": "sys.observe",
                    "scope": {"kind": "name", "value": "audio"}, "reason": "Synthetic restoration",
                }] if pending else [],
                "recent": [{"id": "ap-fixture", "state": decision}] if decision else [],
                "semantics": "Enabled is not granted",
            }
            (fixture / "permission-state.json").write_text(json.dumps(value))
            return value

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
        expected = os_permission_state(False, pending=True)
        assert success(call("permissions_show", {"app_id": "audio-manager"})) == expected
        # Cancelled OS authentication leaves the next authoritative query pending.
        assert success(call("permissions_show", {"app_id": "audio-manager"})) == expected
        for enabled, decision in [(False, "approved"), (True, "approved"), (False, "denied")]:
            expected = os_permission_state(enabled, decision=decision)
            observed = success(call("permissions_show", {"app_id": "audio-manager"}))
            assert observed == expected
            assert observed["permissions"][0]["enabled"] is enabled
            assert observed["permissions"][0]["live_granted"] is False
        before_policy = (fixture / "permission-state.json").read_bytes()
        (fixture / "transport-failure").touch()
        failed = call("permissions_request", {
            "app_id": "audio-manager", "permission_id": "exact-id", "reason": "Transport failure",
        })
        assert failed["result"]["isError"], failed
        assert (fixture / "permission-state.json").read_bytes() == before_policy
        (fixture / "transport-failure").unlink()
        assert success(call("permissions_show", {"app_id": "audio-manager"})) == expected
        assert success(call("permissions_revoke", {
            "app_id": "audio-manager", "permission_id": "exact-id",
        }))["revoked"]
        before = (fixture / "calls").read_bytes()
        for name, args in [
            ("permissions_approve", {"id": "ap-fixture", "confirm": True}),
            ("permissions_decide", {"id": "ap-fixture", "decision": "approve"}),
            ("permissions_request", {"app_id": "audio-manager", "permission_id": "exact-id",
                                     "reason": "forged", "owner_uid": 0}),
            ("permissions_request", {"app_id": "audio-manager", "permission_id": "exact-id",
                                     "reason": "forged", "duration": "forever"}),
            ("permissions_show", {"app_id": "audio-manager", "session": "another-owner"}),
            ("permissions_revoke", {"app_id": "audio-manager"}),
        ]:
            reply = call(name, args)
            assert "error" in reply or reply["result"].get("isError"), reply
        assert (fixture / "calls").read_bytes() == before
        (fixture / "deny").touch()
        assert call("open", {})["result"]["isError"]
        denied = call("permissions_list", {})
        assert denied["result"]["isError"]
        assert "permission fixture denied" in denied["result"]["content"][0]["text"]
        (fixture / "deny").unlink()
        (fixture / "wrong-target").touch()
        assert call("open", {})["result"]["isError"]
        calls = [json.loads(line) for line in (fixture / "calls").read_text().splitlines()]
        assert all(sid == "worker-session" and "app" not in args for args, sid in calls)
        # Exercise the very same client with the human GUI's environment, without
        # initializing a renderer or adding a fixture-only production CLI route.
        artifacts = subprocess.run([
            "cargo", "test", "--locked", "--no-run", "--message-format=json",
            "--manifest-path", str(build_root / "Cargo.toml"),
            "--target-dir", str(target_dir), "--package", "cosmic-settings",
        ], check=True, env=environment, stdout=subprocess.PIPE, text=True)
        tests = [
            entry["executable"]
            for entry in map(json.loads, artifacts.stdout.splitlines())
            if entry.get("reason") == "compiler-artifact" and entry.get("executable")
            and entry["target"]["name"] == "cosmic-settings" and entry["profile"]["test"]
        ]
        assert len(tests) == 1, tests
        human = subprocess.run([
            *command, "--unsetenv", "COS_MCP_SERVER", "--unsetenv", "COS_SESSION",
            "--ro-bind", tests[0], "/usr/bin/settings-permission-client-fixture",
            "--", "/usr/bin/settings-permission-client-fixture", "--ignored", "--exact",
            "permissions::tests::installed_permission_client_uses_closed_environment",
            "--test-threads=1",
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        assert human.returncode == 0, human.stdout + human.stderr
        final_call = json.loads((fixture / "calls").read_text().splitlines()[-1])
        assert final_call == [["--wire=1", "__app-permissions", '{"action":"list"}'], None]
        assert not (fixture / "config").exists()
        print("Settings installed binary/resources: 32 localized entries, schemas/polkit/icons; "
              "seven authenticated MCP tools, owner/session injection and self-approval rejection, "
              "pending/approved/denied restoration with OS query truth, cancelled-authentication pending "
              "and failed-transport behavior, revocation responses; 31 pages, search clamps, fixed launch, denial, "
              "expiry and wrong-target rejection; human and MCP permission clients use sanitized PATH "
              "without CLAW_COS_BIN; no GUI/device/account access")
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
