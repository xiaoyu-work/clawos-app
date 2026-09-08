# Calendar

Local events and Google/Outlook calendar operations, with one business
implementation behind the existing CLI and MCP surface.

Source has moved from Claw OS without changing the `calendar` manifest,
runtime behavior, provider selection or database layout. The OS still owns
capability enforcement, credential access and App data-partition migration.
The complete `panel-calendar` presentation, translations and assets now live
in `native/claw-applet-calendar`. Its library is linked into the OS shell,
which injects a typed, policy-gated agenda provider. Its human-only launcher,
installed identity and grants are unchanged; no extra MCP or account merge
is introduced. See [PROVENANCE.md](PROVENANCE.md) for native licensing.

See [MODULE.md](MODULE.md) for entrypoints and product commands. Development
uses the repository's immutable SDK/runtime and shared-library lock, never a
sibling OS checkout.

Run native tests with `python3 products/calendar/native/build.py test` from
the repository root. This builds against the pinned Claw OS toolkit, not
upstream COSMIC styling. CI runs this independently of Python App contracts.
