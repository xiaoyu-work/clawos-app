# Store

The `pkg` App searches and inspects the local apt catalog, reports installed
packages and submits package changes to the Claw OS broker. Its thirteen
existing CLI operations and MCP tools keep their identities, arguments and
permissions.

Privileged package execution, transaction serialization, audit and rollback
remain OS-owned. This move does not alter the installed package database or
APT update mechanism.

The complete native `cosmic-store` fork now lives in `native/cosmic-store`,
including its original default renderer, Flatpak/PackageKit UI, translations,
resources, nested `flathub-stats` helper and locked dependency graph.
Its four MCP tools retain independent native grants. Read-only queries embed
the same product catalog functions as `pkg`, without calling that App or
borrowing transaction authority. Human UI file handling uses OS policy and
snapshots; window activation uses the fixed OS Store target.

This source move preserves native UI backends rather than merging the apt MCP
catalog with AppStream/Flatpak/PackageKit. No user data, package database, apt
configuration or accounts move. Interactive package operations and visual
acceptance have not been exercised by the synthetic tests.

See [native/PROVENANCE.md](native/PROVENANCE.md) for source origins and licensing.

See [MODULE.md](MODULE.md) for source navigation and commands.
