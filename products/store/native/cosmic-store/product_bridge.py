"""Private adapters over Store's compiled-in catalog and OS policy/snapshots."""

from cos_runtime import policy, snapshot
import shutil
import stat


def dispatch(request):
    operation, args = request["operation"], request["arguments"]
    if operation == "search":
        return backend.cmd_search(["--limit", str(args["limit"]), "--", args["query"]])
    if operation == "installed":
        return backend.cmd_list([])
    if operation == "show":
        return backend.cmd_show([args["name"]])
    if operation == "remove_data":
        if os.environ.get("COS_MCP_SERVER") == "1":
            raise ValueError("human UI data deletion is unavailable in MCP")
        path = args["path"]
        if not isinstance(path, str) or not path or "\0" in path:
            raise ValueError("invalid data path")
        path = os.path.abspath(path)
        policy.require("fs.delete", path=path)
        metadata = os.lstat(path)
        snapshot.snapshot(path, "rm", session_id=os.environ.get("COS_SESSION") or None)
        if stat.S_ISDIR(metadata.st_mode):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return {"removed": path}
    raise ValueError("unknown private Store operation")


try:
    result = dispatch(json.load(sys.stdin))
    print(json.dumps(result))
    if result.get("error"):
        raise SystemExit(1)
except (policy.PolicyError, OSError, ValueError, TypeError, KeyError) as error:
    print(json.dumps({"error": str(error)}))
    raise SystemExit(1)
