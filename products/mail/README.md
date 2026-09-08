# Mail

This product owns the complete Thunderbird **153.2.0esr** source at `comm/`,
the existing shared Mail AI business implementation at `apps/mail-ai/`,
its Thunderbird UI at `extension/`, and the legacy SMTP/Gmail/Outlook
transport at `apps/email/`.

The source moved from Claw OS commit
`0492ea6c13cca3213b1b1bafabeed5e6074ebb44`. See
[PROVENANCE.md](PROVENANCE.md) for the original upstream revisions and licenses.
The native source is not a submodule or a second IMAP/SMTP client.

## Current boundary

The six existing AI operations share one implementation between UI and MCP.
Their installed identity remains `mail-ai`; moving repositories does not
change user consent, accounts, installed paths or native-host authority.
The legacy transport retains the separate installed `email` identity and
provider-specific grants until the explicit product cutover.
Native mailbox/MCP integration, product branding and the later consolidation
of the old `email` and `gateway-email` identities are not complete.

The OS repository retains the native authority launcher, SDK/runtime,
Thunderbird registration and signed package installation. It pins this
repository's revision instead of keeping a second copy of product source.

## Build and test

From this repository root on Linux/WSL:

```bash
python3 tools/test.py mail
python3 tools/stage.py mail --root build/stage
python3 products/mail/build.py prepare
python3 products/mail/build.py bootstrap --application-choice=browser --no-system-changes
python3 products/mail/build.py configure
python3 products/mail/build.py build -j 8
python3 products/mail/build.py package
```

Product contracts fetch only the immutable SDK/runtime dependency recorded in
`platform.lock.json`, never a sibling OS checkout. Native source and objects
must be on the Linux filesystem. The upstream desktop toolchain choice is
called `browser`; `mozconfig` explicitly selects `comm/mail`, not Firefox
artifact mode. Linux `zip` and `unzip` are required.

The native builder refuses a mismatched or modified Firefox platform and
links the product source into `build/mail/gecko/comm`. Toolchain state and
objects stay in ignored `build/mail/`. The build uses unofficial branding and
disables the upstream binary updater; it does not install or modify an
existing Thunderbird profile.

`tools/stage.py` currently assembles the existing Python App and matching XPI,
not an unbuilt native binary. OS packaging adds its authority launcher and
runtime, then applies the existing signing/provenance pipeline.
