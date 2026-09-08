# Mail Extension

Thunderbird UI integration for the [Mail product](../README.md).
`../apps/mail-ai/app.json` owns the six AI operation schemas; Python shared
functions implement them. This UI owns extraction, compose-window integration,
presentation and optional Thunderbird tags, not provider credentials or an
independent mailbox.

`background.js` forwards native requests, `lib/native.js` correlates frames,
`lib/ui.js` supplies UI helpers, and `test_contract.py` executes request builders
with Node fixtures. Run `python3 tools/test.py mail` from the repository root.
Native authority and installed package ownership are tested in Claw OS.
