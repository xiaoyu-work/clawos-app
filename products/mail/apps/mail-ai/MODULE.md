# Mail AI Module

## Purpose and boundaries

Preparatory M1 Mail business layer, still identified as `mail-ai`.
[`README.md`](README.md) describes the contract and limits; the
[product guide](../../MODULE.md) owns the later Mail merger.
This module does not own a mailbox, provider credentials, or App orchestration.

## Key files

| File | Responsibility |
| --- | --- |
| `main.py` | Six typed business functions, shared validation, AI shaping, narrowly scoped memory |
| `app.json` | Six MCP business schemas plus the ordinary `native-host` stdin operation and primary entry |
| `server.py` | Public SDK authenticated MCP binding and MCP result encoding |
| `native_host.py` | Declared primary entry, isolated bootstrap and strict Native Messaging transport |
| `test_main.py` | Business, manifest, authority, real process/framing and ingress parity tests |

Native Messaging and MCP share `main.py`, not one another's dispatchers.
Validate untrusted input before `ai.chat.untrusted`; keep AI budget/safety
handling and `mail-ai` memory scope aligned with the manifest. Native callers
must never construct MCP metadata or use SDK-private authentication methods.
Core owns launcher trust, verified App sessions, owner identity, and consent.
`cos app stdio mail-ai native-host` runs this primary entry through the generic
verified App-operation host. The operation explicitly requests wildcard
`ai.chat.untrusted` for the shared AI gate and `memory.write:self:mail-ai`
for summaries/notable triage; the OS does not infer grants from MCP tools.
Neither a launcher name nor Thunderbird's extension argument is authority.
The six business CLI names still resolve to their exact `server.py` MCP tools.
Ordinary Python non-`main.py` operation execution is unsupported outside the
stdio contract; do not add a `run` wrapper or fallback rewrite.

## Coupled surfaces and tests

Argument changes must update all
[`claw-mail-ai`](../../extension/) callers and their contract
tests in the same change. Installed startup changes also require coordination
with the core launcher, rootfs feature, and development installer.

From the repository root:

```bash
python3 tools/test.py mail
```
