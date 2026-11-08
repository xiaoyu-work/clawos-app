import hashlib
import json

from claw_os_sdk import events
from claw_os_sdk.objects import format_reference
from claw_os_sdk.mcp import App, ToolResult, current_context

import file_plans
import main


app = App.from_manifest()

def _changed(result, path, operation):
    path = main._abs(path)
    reference = format_reference({"app_id": "fs", "object_type": "file", "object_id": path})
    key = "file-" + hashlib.sha256(json.dumps(
        {"operation": operation, "object": reference, "call": current_context().call_id}, sort_keys=True,
    ).encode()).hexdigest()
    try:
        events.publish("file.changed", key, entity_id=path, payload={
            "object": reference, "operation": operation,
        })
    except Exception as error:
        result = {**result, "event_error": str(error), "effects_not_repeated": True}
    return {**result, "artifacts": [reference]}

def _plan_event(result, event_type):
    if result.is_error:
        return result
    value = result.structured_content
    try:
        events.publish(
            event_type, "plan-" + value["plan_id"] + "-" + event_type,
            entity_id=value["path"], payload={"object": value["reference"]},
        )
    except Exception as error:
        result.content.append({
            "type": "text",
            "text": f"Plan operation returned; event publication failed: {error}. Do not repeat the file effect.",
        })
    return result


def _plan_result(handler, *args, **kwargs) -> ToolResult:
    try:
        return ToolResult.structured(handler(*args, **kwargs))
    except file_plans.PlanError as error:
        value = {"error": str(error), "code": error.code}
    except ValueError as error:
        value = {"error": str(error), "code": "invalid_args"}
    except OSError as error:
        value = {"error": f"file plan I/O failed: {error}", "code": "file_plan_io"}
    result = ToolResult.structured(value)
    return ToolResult(content=result.content, is_error=True, structured_content=value)


@app.tool("fs.plan_write")
def plan_write(path: str, content: str, ttl_seconds: int = 3600) -> ToolResult:
    return _plan_event(
        _plan_result(file_plans.plan_write, path, content, ttl_seconds), "file.plan.created",
    )


@app.tool("fs.plan_show")
def plan_show(path: str, plan: str | None = None) -> ToolResult:
    return _plan_result(file_plans.plan_show, path, plan)


@app.tool("fs.plan_apply")
def plan_apply(path: str, plan: str, review: str, confirm: bool) -> ToolResult:
    return _plan_event(_plan_result(
        file_plans.plan_apply, path, plan, review, confirm,
        session_id=current_context().session_id,
    ), "file.changed")


@app.tool("fs.plan_prune")
def plan_prune(path: str, confirm: bool, keep: int = 10) -> ToolResult:
    return _plan_result(file_plans.plan_prune, path, confirm, keep)


@app.tool("fs.ls")
def ls(path: str = ".") -> dict:
    return main.ls(path)


@app.tool("fs.read")
def read(
    path: str,
    offset: int = 0,
    limit: int = 1_000_000,
    start: int | None = None,
    end: int | None = None,
) -> dict:
    return main.read(path, offset, limit, start, end)


@app.tool("fs.write")
def write(path: str, content: str) -> dict:
    return _changed(main.write(path, content, session_id=current_context().session_id), path, "write")


@app.tool("fs.rm")
def rm(path: str) -> dict:
    return _changed(main.rm(path, session_id=current_context().session_id), path, "remove")


@app.tool("fs.mkdir")
def mkdir(path: str) -> dict:
    return _changed(main.mkdir(path, session_id=current_context().session_id), path, "mkdir")


@app.tool("fs.stat")
def stat(path: str) -> dict:
    return main.stat(path)


@app.tool("fs.search")
def search(query: str, path: str = "/workspace") -> dict:
    return main.search(query, path)


@app.tool("fs.tag")
def tag(path: str, tags: list[str]) -> dict:
    return _changed(main.tag(path, tags, session_id=current_context().session_id), path, "tag")


@app.tool("fs.recent")
def recent(n: int = 10) -> dict:
    return main.recent(n)


@app.tool("fs.rename")
def rename(src: str, dst: str) -> dict:
    return _changed(main.rename(src, dst, session_id=current_context().session_id), dst, "rename")


@app.tool("fs.move")
def move(src: str, dst: str) -> dict:
    return _changed(main.move(src, dst, session_id=current_context().session_id), dst, "move")


@app.tool("fs.copy")
def copy(src: str, dst: str) -> dict:
    return _changed(main.copy(src, dst, session_id=current_context().session_id), dst, "copy")


@app.tool("fs.read_bytes")
def read_bytes(path: str, offset: int = 0, limit: int = 4_194_304) -> dict:
    return main.read_bytes(path, offset, limit)


@app.tool("fs.write_bytes")
def write_bytes(path: str, content: str) -> dict:
    return _changed(main.write_bytes(path, content, session_id=current_context().session_id), path, "write_bytes")


if __name__ == "__main__":
    app.serve()
