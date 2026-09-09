from collections.abc import Callable

from claw_os_sdk import kernel
from claw_os_sdk.mcp import App, ToolResult
from main import list_notifications, send

app = App.from_manifest()


def invoke(operation: Callable[[], dict[str, object]]) -> ToolResult:
    try:
        return ToolResult.structured(operation())
    except kernel.KernelDenied as error:
        return ToolResult(
            content=[{"type": "text", "text": str(error)}],
            is_error=True,
            structured_content=error.payload,
        )
    except kernel.KernelUnavailable as error:
        return ToolResult(
            content=[{"type": "text", "text": str(error)}],
            is_error=True,
            structured_content={"code": "unavailable", "error": str(error)},
        )


@app.tool("notify.send")
def notify_send(message: str, urgent: bool = False) -> ToolResult:
    return invoke(lambda: send(message, urgent))

@app.tool("notify.list")
def notify_list(limit: int = 20) -> ToolResult:
    return invoke(lambda: list_notifications(limit))


if __name__ == "__main__":
    app.serve()
