"""Private adapter over the canonical Terminal command implementation."""

from cos_runtime import policy


def dispatch(request):
    operation, arguments = request["operation"], request["arguments"]
    if operation == "run":
        result = backend.cmd_run([
            "--timeout", str(arguments["timeout_secs"]), "--",
            arguments["command"], *arguments["arguments"],
        ])
        if "error" in result and not result.get("timed_out"):
            raise ValueError(result["error"])
        return {
            "stdout": result["stdout"], "stderr": result["stderr"],
            "exit_code": result["exit_code"], "timed_out": result.get("timed_out", False),
        }
    if operation == "which":
        program = arguments["program"]
        result = backend.cmd_which(["--", program])
        if result.get("error") not in (None, "not found"):
            raise ValueError(result["error"])
        return {"program": program, "path": result.get("path"), "found": "path" in result}
    raise ValueError("unknown private Terminal operation")


try:
    print(json.dumps(dispatch(json.load(sys.stdin))))
except (policy.PolicyError, OSError, ValueError, TypeError, KeyError) as error:
    print(json.dumps({"error": str(error)}))
    raise SystemExit(1)
