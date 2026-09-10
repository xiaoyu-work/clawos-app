"""Exercise the installed native executable with fake state and OS services.

Run after `python3 tools/native_build.py launcher build` on Linux with bwrap.
All writes stay under the repository's ignored build directory.
"""

import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from platform_dependency import prepare_exports  # noqa: E402
from stage import IGNORE, stage, stage_shared  # noqa: E402


def main():
    fixture = ROOT / "build/launcher-process-fixture"
    fixture.mkdir()
    process = None
    try:
        libraries = prepare_exports(download=False)
        installed = fixture / "installed"
        stage("launcher", installed, ["cosmic-launcher"])
        python = stage_shared(installed)
        shutil.copytree(libraries["python-sdk"] / "claw_os_sdk", python / "claw_os_sdk", ignore=IGNORE)
        shutil.copytree(libraries["python-runtime"] / "cos_runtime", python / "cos_runtime", ignore=IGNORE)
        applications = fixture / "applications"
        applications.mkdir()
        for name in ("Editor", "Other"):
            (applications / f"{name}.desktop").write_text(
                f"[Desktop Entry]\nType=Application\nName={name}\nExec=never-executed\n"
            )
        broker = fixture / "cos"
        broker.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> /fixture/broker-calls\n"
            "case \"$1:$2:$3\" in\n"
            " --wire=1:__policy:check)\n"
            "  if [ -f /fixture/deny ]; then\n"
            "   echo '{\"ok\":true,\"wire_version\":1,\"data\":{\"decision\":\"deny\",\"summary\":\"fixture denied\"}}'\n"
            "  else\n"
            "   echo '{\"ok\":true,\"wire_version\":1,\"data\":{\"decision\":\"allow\"}}'\n"
            "  fi;;\n"
            " __desktop:launch:--app-id)\n"
            "  if [ -f /fixture/fail ]; then\n"
            "   echo '{\"error\":\"fixture launch failed\"}'; exit 1\n"
            "  fi\n"
            "  echo '{\"launched\":true,\"app_id\":\"Editor\",\"launcher\":\"fixture\"}';;\n"
            " *) exit 99;;\n"
            "esac\n"
        )
        broker.chmod(0o755)
        command = [
            "bwrap", "--die-with-parent", "--unshare-net", "--ro-bind", "/", "/",
            "--dev", "/dev",
            "--tmpfs", "/usr/lib", "--tmpfs", "/run",
            "--tmpfs", "/usr/local/bin",
        ]
        for library in Path("/usr/lib").iterdir():
            if library.name != "cos":
                command.extend(["--ro-bind", str(library), str(library)])
        command += [
            "--bind", str(fixture), "/fixture",
            "--ro-bind", str(installed / "usr/lib/cos"), "/usr/lib/cos",
            "--ro-bind", str(broker), "/usr/local/bin/cos",
            "--setenv", "COS_MCP_SERVER", "1",
            "--setenv", "COS_APP_MANIFEST", "/usr/lib/cos/apps/cosmic-launcher/app.json",
            "--setenv", "COS_DATA_DIR", "/fixture/data",
            "--setenv", "XDG_DATA_HOME", "/fixture",
            "--setenv", "XDG_DATA_DIRS", "/fixture",
            "--setenv", "CLAW_COS_BIN", "/untrusted/must-not-execute",
            "--setenv", "COS_BIN", "/untrusted/must-not-execute",
            "--", str(ROOT / "build/native-target/debug/cosmic-launcher"),
        ]
        # Existing host directories are never changed. Scratch mountpoints
        # live only on the namespace's fresh /run and /usr/lib filesystems.
        command = [part.replace("/fixture", "/run/launcher-fixture") for part in command]
        broker.write_text(broker.read_text().replace("/fixture", "/run/launcher-fixture"))
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
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
            assert selector.select(15), f"native MCP timed out: {method}"
            line = process.stdout.readline()
            if not line:
                raise AssertionError(process.stderr.read())
            response = json.loads(line)
            assert response["id"] == counter
            return response

        def call(tool, arguments):
            return request("tools/call", {
                "name": f"launcher.{tool}", "arguments": arguments,
                "_meta": {"claw-os.dev/call-context": {
                    "wire_version": 1, "call_id": f"fixture-{counter}",
                    "trace_id": "fixture", "session_id": "fixture",
                    "caller": {"kind": "system-agent", "id": "fixture", "owner_uid": 1000},
                }},
            })["result"]

        assert "result" in request("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "native-fixture", "version": "1"},
        })
        process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        process.stdin.flush()
        tools = request("tools/list", {})["result"]["tools"]
        assert len(tools) == 4
        assert "error" in request("tools/call", {"name": "launcher.recent", "arguments": {}})
        assert call("recent", {})["structuredContent"] == {"recent": []}
        assert call("find", {"query": "Editor", "limit": 100})["structuredContent"]["count"] == 1
        assert call("list", {"include_hidden": False})["structuredContent"]["count"] == 2
        (fixture / "deny").touch()
        assert call("list", {})["isError"]
        assert call("open", {"app_id": "Editor"})["isError"]
        (fixture / "deny").unlink()
        assert call("open", {"app_id": "Editor", "extras": ["--unsafe"]})["isError"]
        (fixture / "fail").touch()
        assert call("open", {"app_id": "Editor"})["isError"]
        (fixture / "fail").unlink()
        assert call("recent", {})["structuredContent"] == {"recent": []}
        result = call("open", {"app_id": "Editor", "extras": ["https://example.invalid"]})
        assert not result.get("isError"), result
        assert result["structuredContent"]["launched"] is True
        assert call("recent", {})["structuredContent"]["recent"][0]["app_id"] == "Editor"
        calls = (fixture / "broker-calls").read_text()
        assert "__desktop launch --app-id Editor --uri https://example.invalid" in calls
        assert "__policy check desktop.launch --name Editor" in calls
        assert "app launcher" not in calls
        print("Native executable: authenticated tools, exact policy, errors and isolated history passed")
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
