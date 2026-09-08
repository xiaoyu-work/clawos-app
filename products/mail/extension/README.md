# Mail UI extension

This Thunderbird extension uses the [shared Mail AI implementation](../apps/mail-ai/).
UI and Agent MCP call the same six operations: `summarize`, `smart_reply`,
`smart_compose`, `translate`, `triage` and `chat`. Schemas live only in
[`app.json`](../apps/mail-ai/app.json).

The extension identity remains `claw-mail-ai@claw.os`, and the native host is
`os.claw.mail_ai`. The OS-owned `claw-mail-ai-host` launcher validates the
Thunderbird parent and registers the restricted App session before starting
the canonical `/usr/lib/cos/apps/mail-ai/native_host.py`. This extension does
not manufacture an MCP caller or own model credentials.

Native requests are `{id, verb, args}` objects framed with a four-byte
little-endian length followed by UTF-8 JSON. Replies preserve `id`, `ok` and
the structured `result` or error. See the [business contract](../apps/mail-ai/README.md).

`tools/stage.py mail --root <staging-root>` builds the reproducible XPI alongside
the matching App. The signed Claw OS package installs both and supplies the
native launcher/runtime. Rootfs registration must not overwrite their files.

From the repository root, run `python3 tools/test.py mail`. Fixtures exercise
the real request-building code, not live Thunderbird rendering.
