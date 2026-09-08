# Calendar

Local events and Google/Outlook calendar operations, with one business
implementation behind the existing CLI and MCP surface.

Source has moved from Claw OS without changing the `calendar` manifest,
runtime behavior, provider selection or database layout. The OS still owns
capability enforcement, credential access and App data-partition migration.
The related `panel-calendar` presentation remains in the OS repository until
its own migration.

See [MODULE.md](MODULE.md) for entrypoints and product commands. Development
uses the repository's immutable SDK/runtime and shared-library lock, never a
sibling OS checkout.
