# Mail

This product owns the complete Thunderbird **153.2.0esr** source at `comm/`,
the existing shared Mail AI business implementation at `apps/mail-ai/`,
its Thunderbird UI at `extension/`, and the Thunderbird-backed Agent
client at `apps/email/`. The separate legacy SMTP delivery gateway is retired.

The source moved from Claw OS commit
`0492ea6c13cca3213b1b1bafabeed5e6074ebb44`. See
[PROVENANCE.md](PROVENANCE.md) for the original upstream revisions and licenses.
The native source is not a submodule or a second IMAP/SMTP client.

## Current boundary

The six existing AI operations share one implementation between UI and MCP.
Their installed identity remains `mail-ai`; moving repositories does not
change user consent, accounts, installed paths or native-host authority.
The Agent client retains the installed `email` identity but now reads and sends
through Thunderbird's existing accounts. `email.accounts` lists profile-qualified
account IDs; mailbox operations require an explicit `--account`, without
credential detection or Gmail/Outlook API/SMTP fallback. Separate `mail.read`,
`mail.draft` and `mail.send` grants replace those operation needs; existing
credentials and grants are not copied, deleted or silently converted.
`gateway-email` source and its active App selection are removed explicitly.
Its old credentials and installed user data remain untouched; it is not an
Email fallback or another source-owned mailbox.
The OS broker starts the owner's Thunderbird through its user-session service
manager when necessary. The extension uses native background send/save APIs,
not a model request or a compose-window automation loop.
Product branding, identity consolidation and installed native/GUI acceptance
remain separate; this source change does not publish or install a release.

```bash
cos app email accounts
cos app email folders --account ACCOUNT_ID
cos app email list --account ACCOUNT_ID --unread --max-results 10
cos app email read --account ACCOUNT_ID --id MESSAGE_REFERENCE_ID
cos app email draft_save --account SENDER_ACCOUNT_ID \
  --to user@example.com --subject "Report" --body "Please review."
```

Copy returned IDs rather than Thunderbird's session-local numeric message IDs.
`native_draft --id DRAFT_REFERENCE_ID` returns a complete review fingerprint.
Sending it requires the draft's mailbox `--account`, an explicit
`--sender-account`, the current `--review` and `--confirm`.
These accounts can differ when Thunderbird stores drafts in Local Folders;
rights remain independent. See [MODULE.md](MODULE.md).

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
