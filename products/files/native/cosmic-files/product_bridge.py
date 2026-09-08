"""Private UI adapter over compiled-in product libraries, not an App entrypoint."""

import base64
import json
import os
import sys

from cos_runtime import memory, policy


def dispatch(request):
    operation = request["operation"]
    args = request["arguments"]
    if operation == "document":
        path = args["path"]
        if not isinstance(path, str) or not path or "\0" in path:
            raise ValueError("path must be a nonempty string without NUL")
        result = document.cmd_read([path])
        if "error" in result:
            raise ValueError(result["error"])
        content = result["content"]
        if not content.strip():
            raise ValueError("document produced no extractable text")
        return {"content": content[:100_000]}
    if operation == "recoll":
        return recoll.search(**args)
    if operation == "remember":
        path, text = args["path"], args["text"]
        if not isinstance(path, str) or not isinstance(text, str):
            raise ValueError("summary path and text must be strings")
        head = text.strip().splitlines()
        if not head:
            raise ValueError("summary is empty")
        return memory.remember(
            source="cosmic-files", text=f"Summarised document {path}: {head[0][:200]}",
            kind="note", entity_id=path, tags=["files", "summary"],
        )
    read_operations = {"ls": fs.ls, "stat": fs.stat}
    if operation in read_operations:
        return read_operations[operation](**args)
    mutations = {
        "write": fs.write, "write_bytes": fs.write_bytes, "mkdir": fs.mkdir,
        "rename": fs.rename, "copy": fs.copy, "rm": fs.rm,
    }
    if operation not in mutations:
        raise ValueError("unknown private Files operation")
    # These are human UI mutations, never MCP handlers. A persistent MCP
    # process must not confuse its own environment with a caller's session.
    if os.environ.get("COS_MCP_SERVER") == "1":
        raise ValueError("UI mutations are unavailable in the MCP process")
    if operation == "write_bytes":
        args = {**args, "content": base64.b64encode(bytes(args["content"])).decode("ascii")}
    return mutations[operation](**args, session_id=os.environ.get("COS_SESSION") or None)


def main():
    try:
        result = dispatch(request)
    except (policy.PolicyError, memory.MemoryError, OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({
            "error": str(error),
            "denied": isinstance(error, (policy.PermissionDenied, memory.PermissionDenied)),
        }))
        raise SystemExit(1)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
