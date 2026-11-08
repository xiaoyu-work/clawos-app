"""Assemble product-owned, package-local Web UI resources."""

import json
from pathlib import Path
import re
import stat


SCHEMA = "claw.web-app/v1"
DESCRIPTOR = "web-ui.json"
MAX_BYTES = 8 * 1024 * 1024
EXTENSIONS = {".html", ".js", ".css", ".json", ".svg", ".png", ".webp", ".woff2", ".txt"}


def resources(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Web UI resources must be a source-owned directory")
    result = {}
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*", part)
               for part in relative.parts) or len(relative.parts) > 8:
            raise ValueError("Invalid package-local Web UI resource path")
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode) or path.stat().st_nlink != 1 or path.suffix not in EXTENSIONS:
            raise ValueError("Web UI resources cannot contain links, special nodes or executable payloads")
        content = path.read_bytes()
        total += len(content)
        if total > MAX_BYTES or len(result) >= 256:
            raise ValueError("Web UI resource limit exceeded")
        result[relative] = content
    return result


def stage_ui(source, package, app_id, target, *, kind="product"):
    declaration = package.get("web_ui")
    if declaration is None:
        return
    declared = {"-".join(Path(path).parts[1:]) for path in package["apps"]}
    if not isinstance(declaration, dict) or set(declaration) != {"source", "apps"} or (
        declaration["source"] != "web" or not isinstance(declaration["apps"], list)
        or not declaration["apps"] or len(declaration["apps"]) != len(set(declaration["apps"]))
        or any(value not in declared for value in declaration["apps"])
    ):
        raise ValueError("Web UI ownership must explicitly select this source's App identities")
    if app_id not in declaration["apps"]:
        return
    source = Path(source)
    source_files = resources(source / "web")
    if Path("index.html") not in source_files or Path("app.js") not in source_files:
        raise ValueError("A product Web UI requires its own index.html and app.js")
    shared = source.parents[1] / "shared" / "web"
    shared_files = resources(shared)
    payload = {
        **source_files,
        **{Path("shared") / path: content for path, content in shared_files.items()},
    }
    if len(payload) != len(source_files) + len(shared_files):
        raise ValueError("Product Web UI resources collide with common presentation resources")
    target = Path(target)
    if (target / "web").exists() or (target / DESCRIPTOR).exists():
        raise ValueError("Web UI assembly cannot replace an existing App payload")
    manifest = json.loads((target / "app.json").read_text())
    if manifest["id"] != app_id:
        raise ValueError("Web UI must retain its owning App identity")
    metadata = {
        "schema": SCHEMA, "app_id": app_id, "source_kind": kind,
        "source_name": source.name, "title": manifest.get("name", app_id),
        "description": manifest.get("summary", ""), "entry": "web/index.html",
    }
    for relative, content in payload.items():
        path = target / "web" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(0o644)
    (target / DESCRIPTOR).write_text(json.dumps(metadata, ensure_ascii=True, indent=2) + "\n")
    (target / DESCRIPTOR).chmod(0o644)


def read_descriptor(root, manifest):
    root = Path(root)
    path = root / DESCRIPTOR
    if not path.is_file():
        return None
    if path.is_symlink() or path.stat().st_size > 16 * 1024:
        raise ValueError("Invalid Web UI descriptor")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict) or set(value) != {
        "schema", "app_id", "source_kind", "source_name", "title", "description", "entry",
    } or value["schema"] != SCHEMA or value["app_id"] != manifest["id"] or (
        value["source_kind"] not in ("product", "capability")
        or not isinstance(value["source_name"], str)
        or not re.fullmatch(r"[a-z][a-z0-9-]*", value["source_name"])
        or value["entry"] != "web/index.html"
    ):
        raise ValueError("Web UI descriptor does not bind its App and source")
    resources(root / "web")
    if not (root / value["entry"]).is_file():
        raise ValueError("Web UI entry is missing")
    return value
