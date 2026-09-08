"""Four native tools bound to the embedded shared product implementation."""

from claw_os_sdk.mcp import App


def _native_limit(value: int, maximum: int) -> int:
    if type(value) is not int:
        raise ValueError("limit must be an integer")
    return max(1, min(value, maximum))


app = App.from_manifest(os.environ["COS_APP_MANIFEST"])


@app.tool("launcher.find")
def launcher_find(query: str, limit: int = 10) -> dict[str, object]:
    return find(query, _native_limit(limit, 50))


@app.tool("launcher.list")
def launcher_list(include_hidden: bool = False) -> dict[str, object]:
    return list_apps(include_hidden=include_hidden)


@app.tool("launcher.open")
def launcher_open(app_id: str, extras: list[str] | None = None) -> dict[str, object]:
    return open_extras(app_id, extras)


@app.tool("launcher.recent")
def launcher_recent(limit: int = 20) -> dict[str, object]:
    return recent(_native_limit(limit, 200))


if __name__ == "__main__":
    app.serve()
