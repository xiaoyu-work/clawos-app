"""pkg — Declarative capability management for Claw OS.

Say what you need, not how to install it.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time

# Keep credentials out of the OS package client process.
from _shared.env_scrub import scrub_env  # noqa: E402

from cos_runtime import policy  # noqa: E402
from claw_os_sdk import kernel  # noqa: E402


DEFAULT_SEARCH_LIMIT = 25
MAX_SEARCH_LIMIT = 100

# Retained package requests and bounded metadata queries use separate deadlines.
QUERY_TIMEOUT_SECS = 60
INSTALL_TIMEOUT_SECS = int(os.environ.get("CLAW_PKG_INSTALL_TIMEOUT", "900"))
PACKAGE_NAME_RE = re.compile(
    r"^[a-z0-9][a-z0-9+.-]*(?::[a-z0-9][a-z0-9-]*)?$"
)


def _valid_package_name(package):
    return (
        isinstance(package, str)
        and len(package) <= 255
        and PACKAGE_NAME_RE.fullmatch(package) is not None
    )


def _cos_binary():
    explicit = os.environ.get("COS_BIN")
    if explicit:
        return explicit
    return shutil.which("cos")


def _package_query(action, *arguments):
    binary = _cos_binary()
    if not binary:
        return {"error": "cos binary not found; package catalog provider unavailable"}
    try:
        return kernel.call_json_with_stdin_binary(
            binary,
            ["__package_query", action, *arguments],
            b"",
            deadline_unix_ms=time.time_ns() // 1_000_000 + QUERY_TIMEOUT_SECS * 1000,
        )
    except kernel.KernelDenied as error:
        return {"error": str(error), "denial": error.payload}
    except kernel.KernelUnavailable as error:
        return {"error": f"package catalog provider unavailable: {error}"}


def _package_broker(action, package=None, version=None, packages=None):
    """Run one privileged package action through clawd."""
    cos_bin = _cos_binary()
    if not cos_bin:
        return {"error": "cos binary not found; privileged package broker unavailable"}
    payload_action = action not in ("update-index", "hold", "unhold")
    argv = [cos_bin, "__package"]
    if payload_action:
        argv.append("--retained")
    argv.append(action)
    if package is not None:
        argv.append(package)
    if version is not None:
        argv.append(version)
    if packages is not None:
        argv.extend(packages)
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT_SECS,
            stdin=subprocess.DEVNULL,
            env=scrub_env(),
            check=False,
        )
    except PermissionError as exc:
        return {"error": str(exc)}
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    except subprocess.TimeoutExpired:
        return {"error": f"package broker exceeded {INSTALL_TIMEOUT_SECS}s"}

    payload_text = (result.stdout or "").strip() or (result.stderr or "").strip()
    try:
        payload = json.loads(payload_text) if payload_text else {}
    except json.JSONDecodeError:
        return {"error": "package broker returned invalid JSON"}
    if result.returncode != 0 and "error" not in payload:
        payload["error"] = (
            payload.get("stderr_tail")
            or f"package broker exited {result.returncode}"
        )
    if payload_action and not payload.get("error"):
        request = payload.get("request_id")
        if (
            payload.get("accepted") is not True
            or payload.get("status") != "accepted"
            or not isinstance(request, str)
            or not re.fullmatch(r"[a-f0-9]{32}", request)
        ):
            return {"error": "Root package handoff was not confirmed; inspect status before retrying"}
    return payload


def _apt_install(packages):
    """Submit one retained transaction before the caller can be retired."""
    installed = []
    failed = []
    errors = {}
    pending = []
    for pkg in packages:
        if not _valid_package_name(pkg):
            failed.append(pkg)
            errors[pkg] = "invalid Debian package name"
            continue
    valid = [pkg for pkg in packages if pkg not in failed]
    if valid:
        payload = _package_broker("ensure-packages", packages=valid)
        if payload.get("error"):
            failed.extend(valid)
            errors.update({pkg: payload["error"] for pkg in valid})
        else:
            pending.append({**payload, "packages": valid})
    return installed, failed, errors, pending


def cmd_need(args):
    """Ensure packages are installed, only installing what's missing."""
    if not args:
        return {"error": "need requires at least one package name"}
    if len(args) > 128:
        return {"error": "need accepts at most 128 packages per retained transaction"}

    for pkg in args:
        if not _valid_package_name(pkg):
            return {"error": f"invalid Debian package name: {pkg!r}"}
        policy.require("sys.package", name=pkg)

    installed, failed, errors, pending = _apt_install(args)

    response = {
        "installed": installed,
        "already_present": [],
        "failed": failed,
    }
    if errors:
        response["errors"] = errors
    if pending:
        response["status"] = "accepted"
        response["preflight"] = "retained"
        response["transactions"] = pending
    return response


def cmd_has(args):
    """Check if a capability is available."""
    if not args:
        return {"error": "has requires a name argument"}

    name = args[0]
    if not name or name.startswith("-") or "/" in name or "\x00" in name:
        return {"error": f"invalid package or command name: {name!r}"}
    policy.require("sys.observe", name=name)

    return _package_query("available", name)


def _parse_search_args(args):
    """Pull out --limit and return (query, limit)."""
    from canonical_argv import parse_canonical_argv
    query_parts, options = parse_canonical_argv(
        args,
        value_flags={"limit"},
    )
    limit = int(options.get("limit", DEFAULT_SEARCH_LIMIT))
    if limit <= 0:
        raise ValueError("--limit must be positive")
    if limit > MAX_SEARCH_LIMIT:
        limit = MAX_SEARCH_LIMIT
    return " ".join(query_parts).strip(), limit


def cmd_search(args):
    """Search the apt catalog for packages whose name or description
    matches the query. Read-only browse over the catalog the system
    already has indexed — use this when the user asks "what can I
    install to do X?" Pair with `show` for details and `need` to
    install.
    """
    if not args:
        return {"error": "search requires a query"}

    try:
        query, limit = _parse_search_args(args)
    except ValueError as exc:
        return {"error": str(exc)}

    if not query:
        return {"error": "search requires a query"}

    policy.require("sys.observe", name="packages")

    return {"results": [], **_package_query("search", query, str(limit))}


def cmd_show(args):
    """Show detailed metadata for a single package from the apt
    catalog: version, summary, full description, homepage,
    section, size, depends. Use after `search` to vet a candidate
    before `need`.
    """
    if not args:
        return {"error": "show requires a package name"}

    name = args[0]
    if not _valid_package_name(name):
        return {"name": name, "found": False, "error": "invalid Debian package name"}
    policy.require("sys.observe", name=name)

    return {"name": name, "found": False, **_package_query("show", name)}


def cmd_list(args):
    """List installed packages through the controlled OS reader."""
    policy.require("sys.observe", name="packages")
    return {"packages": [], **_package_query("installed")}


def _single_package_action(command, args):
    if len(args) != 1 or not _valid_package_name(args[0]):
        return {"error": f"{command} requires one valid Debian package name"}
    package = args[0]
    policy.require("sys.package", name=package)
    return _package_broker(command, package)


def cmd_install_version(args):
    if len(args) != 2 or not _valid_package_name(args[0]):
        return {"error": "install-version requires <package> <version>"}
    package, version = args
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:+~-]{0,254}", version):
        return {"error": f"invalid Debian package version: {version!r}"}
    policy.require("sys.package", name=package)
    return _package_broker("install-version", package, version)


def cmd_update(args):
    if args:
        return {"error": "update takes no arguments"}
    policy.require("sys.package", wild=True)
    return _package_broker("update-index")


def cmd_upgrade_all(args):
    if args:
        return {"error": "upgrade-all takes no arguments"}
    policy.require("sys.package", wild=True)
    return _package_broker("upgrade-all")


def run(command, args):
    """Entry point called by the cos router."""
    if command != "search":
        from canonical_argv import parse_canonical_argv
        try:
            args, _ = parse_canonical_argv(args)
        except ValueError as error:
            return {"error": str(error)}
    commands = {
        "need": cmd_need,
        "has": cmd_has,
        "list": cmd_list,
        "search": cmd_search,
        "show": cmd_show,
        "remove": lambda values: _single_package_action("remove", values),
        "purge": lambda values: _single_package_action("purge", values),
        "upgrade": lambda values: _single_package_action("upgrade", values),
        "hold": lambda values: _single_package_action("hold", values),
        "unhold": lambda values: _single_package_action("unhold", values),
        "install-version": cmd_install_version,
        "update": cmd_update,
        "upgrade-all": cmd_upgrade_all,
    }
    handler = commands.get(command)
    if handler is None:
        return {"error": f"unknown command: {command}"}
    try:
        return handler(args)
    except policy.PermissionDenied as denied:
        return {"error": str(denied), "denial": denied.denial}
    except policy.PolicyUnavailable as exc:
        return {"error": f"capability check failed: {exc}"}
