"""Human UI operations only; policy, snapshots and credentials stay OS-owned."""

import json
import os
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
from cos_runtime import policy, snapshot
from _shared.env_scrub import scrub_env


def path_argument(args, name):
    value = args[name]
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("invalid Settings path")
    return os.path.abspath(value)


def run(argv, timeout):
    if (not isinstance(argv, list) or not argv or not argv[0]
            or any(not isinstance(arg, str) or "\0" in arg for arg in argv)
            or type(timeout) is not int or not 1 <= timeout <= 300):
        raise ValueError("invalid Settings command")
    policy.require("proc.spawn", name=argv[0])
    output = [bytearray(), bytearray()]
    with subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, env=scrub_env(),
                          start_new_session=True) as child, selectors.DefaultSelector() as selector:
        selector.register(child.stdout, selectors.EVENT_READ, 0)
        selector.register(child.stderr, selectors.EVENT_READ, 1)
        deadline = time.monotonic() + timeout
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Settings command timed out")
                for key, _ in selector.select(min(remaining, 0.1)):
                    block = os.read(key.fileobj.fileno(), 65536)
                    if not block:
                        selector.unregister(key.fileobj)
                    else:
                        buffer = output[key.data]
                        buffer.extend(block[:max(0, 1_000_000 - len(buffer))])
            code = child.wait(timeout=max(0.001, deadline - time.monotonic()))
        finally:
            # Also stop descendants that inherited the pipes, on timeout/error.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
    return {"exit_code": code, "stdout": output[0].decode(errors="replace"),
            "stderr": output[1].decode(errors="replace")}


def dispatch(request):
    if os.environ.get("COS_MCP_SERVER") == "1":
        raise PermissionError("human Settings access is unavailable in MCP")
    operation, args = request["operation"], request["arguments"]
    if operation == "run":
        return run(args["argv"], args["timeout"])
    if operation not in {"mkdir", "remove", "rename"}:
        raise ValueError("unknown human Settings operation")
    path = path_argument(args, "path")
    destination = path_argument(args, "destination") if operation == "rename" else None
    policy.require("fs.delete" if operation in {"remove", "rename"} else "fs.write", path=path)
    if destination is not None:
        policy.require("fs.write", path=destination)
    sid = os.environ.get("COS_SESSION") or None
    if destination is not None:
        snapshot.snapshot_pair(path, destination, "rename", session_id=sid)
    else:
        snapshot.snapshot(path, "rm" if operation == "remove" else operation, session_id=sid)
    if operation == "mkdir":
        os.makedirs(path, exist_ok=True)
    elif operation == "remove":
        if stat.S_ISDIR(os.lstat(path).st_mode):
            shutil.rmtree(path)
        else:
            os.remove(path)
    else:
        os.rename(path, destination)
    return {"completed": True}


if __name__ == "__main__":
    try:
        print(json.dumps(dispatch(json.load(sys.stdin))))
    except (policy.PolicyError, OSError, ValueError, TypeError, KeyError,
            subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error), "denied": isinstance(error, PermissionError)
                          or isinstance(error, policy.PolicyError)}))
        raise SystemExit(1)
