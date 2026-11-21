"""Read and render pages in the OS broker's private Helium process.

The desktop profile and renderer pipe are never exposed to this App.

    cos app web read URL                 -> {url, title, text, links, engine}
    cos app web read URL --html          -> {url, title, html, engine}
    cos app web read URL --eval EXPR     -> {url, result}
    cos app web scrape URL...            -> {results: [...], total_time_ms, ...}
    cos app web screenshot URL --output P -> {ok, output, bytes, ...}
    cos app web submit URL --data ...    -> {url, status, body}  (urllib POST)
"""

import base64
import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from _shared.safe_http import canonical_url, host_scope, open_url, parse_url  # noqa: E402

from claw_os_sdk import ai  # noqa: E402
from cos_runtime import browser_bridge, memory, policy  # noqa: E402

TIMEOUT = int(os.environ.get("COS_WEB_TIMEOUT", "30"))
DEFAULT_MAX_LENGTH = int(os.environ.get("COS_WEB_MAX_CONTENT_LENGTH", "50000"))
USER_AGENT = "cos/" + os.environ.get("COS_VERSION", "0.1.0")
MAX_RENDER_TIMEOUT = 55
MAX_SCREENSHOT = 4 * 1024 * 1024


# ---------------------------------------------------------------------------
# JS payload — extract {title, text, links} from rendered DOM in one pass.
# Escape \t/\n/\s as raw backslash sequences so V8 sees JS escapes, not Python.
# ---------------------------------------------------------------------------

_EXTRACT_JS = r"""(function(){
  function blockText(el){
    if(!el) return '';
    if(el.nodeType===3) return el.textContent||'';
    if(el.nodeType!==1) return '';
    var tag=(el.tagName||'').toLowerCase();
    if(tag==='script'||tag==='style'||tag==='noscript'||tag==='template') return '';
    var s='';
    var cn=el.childNodes||[];
    for(var i=0;i<cn.length;i++) s+=blockText(cn[i]);
    var blocks=['p','div','section','article','header','footer','nav','main','aside','h1','h2','h3','h4','h5','h6','li','tr','blockquote','pre','br','hr'];
    if(blocks.indexOf(tag)!==-1) s+='\n';
    return s;
  }
  var body=document.body||document.documentElement;
  var raw=blockText(body);
  var text=raw.replace(/[\t ]+/g,' ').replace(/\n{3,}/g,'\n\n').replace(/^\s+|\s+$/g,'');
  var anchors=document.querySelectorAll?document.querySelectorAll('a[href]'):[];
  var links=[];
  for(var i=0;i<anchors.length&&i<500;i++){
    var a=anchors[i];
    var href=a.getAttribute('href')||'';
    var t=(a.textContent||'').replace(/\s+/g,' ').replace(/^ +| +$/g,'');
    if(href) links.push({href:href,text:t});
  }
  return {title:document.title||'',text:text,links:links};
})()"""


def _render(url, output, timeout, *, selector=None, user_agent=None):
    return browser_bridge.request(
        "render", url=url, output=output, timeout_secs=min(timeout, MAX_RENDER_TIMEOUT),
        selector=selector, user_agent=user_agent,
    )


# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

def _parse_args(args, flags):
    """Parse --flag value (and --bool-flag) from args. flags: {name: default}.

    A default of True/False marks the flag as boolean (no value consumed).
    Returns (positional_args, parsed_flags).
    """
    positional = []
    result = dict(flags)
    i = 0
    while i < len(args):
        cur = args[i]
        if cur.startswith("--"):
            key = cur[2:]
            if key in flags:
                if isinstance(flags[key], bool):
                    result[key] = True
                    i += 1
                    continue
                if i + 1 < len(args):
                    result[key] = args[i + 1]
                    i += 2
                    continue
                i += 1
                continue
        positional.append(cur)
        i += 1
    return positional, result


def _normalize_url(url):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return canonical_url(parse_url(url))


def _host_of(url):
    """Extract host[:port] from a normalized URL, or None if invalid."""
    try:
        return host_scope(parse_url(url))
    except ValueError:
        return None


def _truncate(s, n):
    if isinstance(s, str) and len(s) > n:
        return s[:n] + "\n\n[truncated]"
    return s


# ---------------------------------------------------------------------------
# AI summarisation prompt
# ---------------------------------------------------------------------------

_SUMMARIZE_SYSTEM = (
    "You are a concise summariser. Read the user's text and reply with "
    "exactly 3 short bullet lines, no preamble."
)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _cmd_read(args):
    """Render a URL and return text, links and title."""
    if not args:
        return {"error": "usage: cos web read <url> [--selector CSS] "
                "[--wait CSS] [--timeout SEC] [--max-length N] [--html] [--eval JS]"}

    positional, flags = _parse_args(args, {
        "selector": None,
        "wait": None,
        "timeout": str(TIMEOUT),
        "max-length": str(DEFAULT_MAX_LENGTH),
        "html": False,
        "eval": None,
        "user-agent": None,
    })

    if not positional:
        return {"error": "usage: cos web read <url>"}

    url = _normalize_url(positional[0])
    host = _host_of(url)
    if host is None:
        return {"error": f"invalid URL: {url}"}
    policy.require("net.dial", host=host)
    try:
        timeout_secs = int(flags["timeout"])
    except (TypeError, ValueError):
        timeout_secs = TIMEOUT
    try:
        max_length = int(flags["max-length"])
    except (TypeError, ValueError):
        max_length = DEFAULT_MAX_LENGTH

    output = {"kind": "html"} if flags["html"] else {
        "kind": "eval", "expression": flags["eval"] or _EXTRACT_JS,
    }
    data = _render(url, output, timeout_secs, selector=flags["wait"] or flags["selector"],
                   user_agent=flags["user-agent"])["result"]
    if flags["html"]:
        return {"url": url, "title": "", "html": _truncate(data, max_length), "engine": "helium"}

    if flags["eval"]:
        return {"url": url, "result": data, "engine": "helium"}
    if not isinstance(data, dict):
        return {"error": "Helium returned no readable page", "url": url}

    return {
        "url": url,
        "title": data.get("title", ""),
        "text": _truncate(data.get("text", ""), max_length),
        "links": data.get("links", []),
        "engine": "helium",
    }


def _cmd_summarize(args):
    """Fetch a URL and pipe its extracted text through the AI gate."""
    if not args:
        return {"error": "usage: cos web summarize <url>"}

    # Coarse-grained capability check — fail fast before fetching the
    # page if the agent doesn't actually have AI access.
    policy.require("ai.chat.untrusted", wild=True)

    read_result = _cmd_read(args)
    if isinstance(read_result, dict) and "error" in read_result:
        return read_result

    text = read_result.get("text", "") if isinstance(read_result, dict) else ""
    url = read_result.get("url", args[0]) if isinstance(read_result, dict) else args[0]
    title = read_result.get("title", "") if isinstance(read_result, dict) else ""
    if not text.strip():
        return {"error": "page produced no extractable text", "url": url}

    try:
        response = ai.chat(
            prompt=text,
            origin="external-content",
            system=_SUMMARIZE_SYSTEM,
            max_units=4000,
        )
    except ai.AiBudgetExceeded as exc:
        return {"error": "AI budget exceeded for this app", "detail": exc.payload}
    except ai.AiSafetyViolation as exc:
        return {"error": "safety violation", "detail": exc.payload}
    except ai.AiDenied as exc:
        return {"error": "AI call denied", "detail": exc.payload}
    except ai.AiUnavailable as exc:
        return {"error": f"AI unavailable: {exc}"}
    except ai.AiError as exc:
        return {"error": str(exc)}

    out = {
        "url": url,
        "title": title,
        "summary": response.text,
        "source_chars": len(text),
        "model": response.model,
        "provider": response.provider,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "units": response.usage.units,
        },
        "budget": {
            "period": response.budget.period,
            "units_used": response.budget.units_used,
            "units_cap": response.budget.units_cap,
        },
        "review": {
            "safety": response.review.safety,
            "prompt_redacted": response.review.prompt_redacted,
        },
    }
    _remember_summary(url, title, response.text)
    return out


def _remember_summary(url, title, summary):
    try:
        if not summary or not url:
            return
        first = summary.strip().splitlines()
        head = first[0] if first else ""
        if len(head) > 200:
            head = head[:197] + "..."
        label = title or url
        memory.remember(
            source="web",
            text=f"Summarised page {label}: {head}",
            kind="note",
            entity_id=url,
            tags=["web", "summary"],
            link=f"cos app web read {url}",
        )
    except memory.MemoryError:
        pass


def _cmd_screenshot(args):
    """Capture a screenshot in Helium; publish only to the approved path."""
    if not args:
        return {"error": "usage: cos web screenshot <url> --output PATH "
                "[--width W] [--height H] [--full-page] [--timeout SEC]"}

    positional, flags = _parse_args(args, {
        "output": None,
        "width": "1280",
        "height": "720",
        "full-page": False,
        "timeout": "60",
    })

    if not positional:
        return {"error": "usage: cos web screenshot <url> --output PATH"}
    url = _normalize_url(positional[0])
    output = flags["output"]
    if not output:
        return {"error": "missing --output PATH"}

    host = _host_of(url)
    if host is None:
        return {"error": f"invalid URL: {url}"}
    output_abs = os.path.realpath(output)
    policy.require("net.dial", host=host)
    policy.require("fs.write", path=output_abs)

    try:
        width = int(flags["width"])
        height = int(flags["height"])
        timeout_secs = int(flags["timeout"])
    except (TypeError, ValueError):
        return {"error": "width/height/timeout must be integers"}

    result = _render(url, {
        "kind": "screenshot", "width": width, "height": height, "full_page": flags["full-page"],
    }, timeout_secs)
    encoded = result.get("data")
    if not isinstance(encoded, str) or len(encoded) > ((MAX_SCREENSHOT + 2) // 3) * 4:
        return {"error": "Helium screenshot is missing or oversized", "url": url}
    try:
        png = base64.b64decode(encoded, validate=True)
    except ValueError:
        return {"error": "Helium returned invalid screenshot data", "url": url}
    if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) > MAX_SCREENSHOT:
        return {"error": "Helium returned an invalid or oversized PNG", "url": url}
    try:
        with open(output_abs, "xb", opener=_private_create) as target:
            target.write(png)
    except OSError as exc:
        return {"error": f"cannot save screenshot: {exc.strerror}", "url": url}
    return {"ok": True, "url": url, "output": output_abs, "bytes": len(png)}


def _private_create(path, flags):
    return os.open(path, flags | os.O_NOFOLLOW, 0o600)


def _cmd_scrape(args):
    """Render separately authorized pages with bounded concurrency."""
    if not args:
        return {"error": "usage: cos web scrape <url> [<url>...] "
                "[--eval JS] [--concurrency N] [--timeout SEC]"}

    positional, flags = _parse_args(args, {
        "eval": _EXTRACT_JS,
        "concurrency": "10",
        "timeout": "60",
        "format": "json",
    })

    urls = [_normalize_url(u) for u in positional]
    if not urls:
        return {"error": "no URLs given"}

    for u in urls:
        host = _host_of(u)
        if host is None:
            return {"error": f"invalid URL: {u}"}
        policy.require("net.dial", host=host)

    try:
        concurrency = int(flags["concurrency"])
        timeout_secs = int(flags["timeout"])
    except (TypeError, ValueError):
        return {"error": "concurrency/timeout must be integers"}

    if concurrency < 1 or len(urls) > 10:
        return {"error": "render batch requires positive concurrency and at most 10 URLs"}
    concurrency = min(concurrency, 2)

    def fetch(index_url):
        index, url = index_url
        started = time.monotonic()
        try:
            value = _render(url, {"kind": "eval", "expression": flags["eval"]}, timeout_secs)
            row = {"title": value["title"], "eval": value["result"], "worker": index}
        except browser_bridge.BrowserBridgeError as exc:
            row = {"error": str(exc)}
        return {"url": url, "time_ms": int((time.monotonic() - started) * 1000), **row}

    start = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(fetch, enumerate(urls)))
    elapsed = int((time.monotonic() - start) * 1000)
    if flags["format"] != "json":
        return {"raw": "\n".join(
            f'{row["time_ms"]}ms\t{row["url"]}\t'
            + (json.dumps(row["eval"], ensure_ascii=False) if row.get("eval") is not None
               else row.get("title", row.get("error", "")))
            for row in results
        )}
    return {
        "total_urls": len(urls), "concurrency": concurrency, "total_time_ms": elapsed,
        "avg_time_ms": elapsed / len(urls), "results": results,
    }


def _cmd_submit(args):
    """POST form data via stdlib urllib (no JS render needed for typical forms)."""
    if not args:
        return {"error": "usage: cos web submit <url> --data '{...}' [--method POST]"}

    positional, flags = _parse_args(args, {
        "data": None,
        "method": "POST",
        "timeout": str(TIMEOUT),
    })
    if not positional:
        return {"error": "usage: cos web submit <url> --data '{...}'"}

    url = _normalize_url(positional[0])
    host = _host_of(url)
    if host is None:
        return {"error": f"invalid URL: {url}"}

    raw = flags["data"] or ""
    method = (flags["method"] or "POST").upper()
    try:
        timeout_secs = int(flags["timeout"])
    except (TypeError, ValueError):
        timeout_secs = TIMEOUT

    payload = None
    content_type = None
    if raw:
        try:
            obj = json.loads(raw)
            payload = urllib.parse.urlencode(obj).encode("utf-8")
            content_type = "application/x-www-form-urlencoded"
        except (ValueError, json.JSONDecodeError):
            payload = raw.encode("utf-8")
            content_type = "application/x-www-form-urlencoded"

    try:
        req = urllib.request.Request(url, data=payload, method=method)
        req.add_header("User-Agent", USER_AGENT)
        if content_type:
            req.add_header("Content-Type", content_type)
        resp = open_url(req, timeout=timeout_secs)[0]
        body = resp.read().decode("utf-8", errors="replace")
        return {"url": resp.url, "status": resp.status, "body": _truncate(body, DEFAULT_MAX_LENGTH)}
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}", "url": url}
    except urllib.error.URLError as e:
        return {"error": f"could not submit: {e.reason}", "url": url}
    except policy.PolicyError:
        raise
    except Exception as e:
        return {"error": str(e), "url": url}


# ---------------------------------------------------------------------------
# Schema (advertised to agents via `cos app web --schema`)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(command, args):
    """Entry point called by cos."""
    from canonical_argv import normalize_canonical_argv
    args = normalize_canonical_argv(args, bool_flags={"html", "full-page"})
    handlers = {
        "read": _cmd_read,
        "scrape": _cmd_scrape,
        "screenshot": _cmd_screenshot,
        "submit": _cmd_submit,
        "summarize": _cmd_summarize,
    }
    handler = handlers.get(command)
    if handler is None:
        return {"error": f"unknown command: {command}"}
    try:
        return handler(args)
    except policy.PermissionDenied as denied:
        return {"error": str(denied), "denial": denied.denial}
    except policy.PolicyUnavailable as exc:
        return {"error": f"capability check failed: {exc}"}
    except (browser_bridge.BrowserBridgeError, ValueError) as exc:
        return {"error": str(exc)}


def main():
    argv = sys.argv[1:]

    if not argv:
        print(json.dumps({
            "error": "usage: cos app web <read|scrape|screenshot|submit|summarize> [args...]",
            "commands": ["read", "scrape", "screenshot", "submit", "summarize"],
        }))
        return

    cmd, rest = argv[0], argv[1:]
    result = run(cmd, rest)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if isinstance(result, dict) and "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
