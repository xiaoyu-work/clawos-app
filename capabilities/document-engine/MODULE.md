# Document Engine Shared-Capability Client

This is a shared-capability source group, not a Documents business product.
`package.json` explicitly declares `kind: "shared-capability-client"`. It owns
the complete legacy `doc` facade; storage, filesystem policy/snapshots, the
public SDK, AI consent/budget/provider/audit authority and memory remain OS-owned.

| Path | Responsibility |
| --- | --- |
| `apps/doc/app.json` | Unchanged `doc` identity, six CLI/MCP operations, bindings, dependencies, grants and AI declaration |
| `apps/doc/main.py` | Existing Doc AI presentation and dispatch over the declared parser library |
| `apps/doc/server.py` | Owning-client manifest-operation MCP bridge through the pinned OS SDK/runtime |
| `apps/doc/test_main.py` | Descriptor/conversion regressions and real manifest-bound SDK dispatch with fake policy/AI |
| `package.json` | App/test selection and explicit Files `claw_files` library dependency for `doc` |

The parser/converter remains the single
[`products/files/python/claw_files/document.py`](../../products/files/python/claw_files/document.py)
implementation. No call to `fs`, `docs` or `cosmic-files` is involved. Tests
resolve its named export and the immutable OS SDK/runtime dependency, never a
sibling checkout. Doc-only staging installs `doc` and `claw_files`, not the
Files Apps or any native UI. Files/Doc co-staging refuses conflicting libraries.
The OS supplies SDK/runtime; the separately staged App common runtime supplies
`canonical_argv` from the same `/usr/lib/cos/python` import root.

Read/info retain their exact file/metadata checks and descriptor-safe behavior;
convert retains its existing read/write declaration and output behavior.
Summarize/explain/rewrite keep the `external-content` origin, strict safety,
200,000-unit monthly App budget and existing per-call bounds. Summary memory
remains `doc`-scoped under the unchanged manifest. No data or grants move, and
source grouping neither retires the identity nor completes backend redesign.
First-party source remains covered by the repository root license.

From the repository root on Linux/WSL:

```bash
python3 tools/test.py --capability document-engine
python3 tools/test.py files --capability document-engine
python3 tools/stage.py document-engine --kind capability --root build/doc-stage
```

The optional real PDF/DOCX/XLSX/PPTX fixture needs the Python parser packages
already declared in `apps/doc/app.json` (the capability CI job installs them);
fake-format and synthetic text cases do not require them. These contracts do
not claim desktop or image acceptance.
