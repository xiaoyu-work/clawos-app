# Notifications provenance

The complete original 40-file Claw OS fork, together with its newly added
native tests/presentation fixture and `apps/cosmic-notifications/app.json`,
was copied from `xiaoyu-work/claw-os` commit
`f7ffabf329ab8e1ec46e131ddd1ed2800060d13a`, `desktop/notifications/`.

Upstream is `https://github.com/pop-os/cosmic-notifications`, originally
vendored at `a899bfbc6715`. The original GPL-3.0 license/copyright text,
executable modes, nested configuration/util crates, standalone Cargo lock,
optional/default graph, Debian/Nix/hook/build metadata and upstream repository
files are preserved. `native/LICENSE` is byte-identical to the original
`native/cosmic-notifications/LICENSE.md`.
One extra trailing blank line in the upstream PR template was normalized for
repository diff checks; its content is unchanged.

Claw-specific changes replace isolated MCP's unusable direct session bus with
bounded OS notification intent, bind native desktop handles to their senders,
correct close signals/replacement timers, reclaim retired presentation handles,
support sender-local connection lifetime, and expose real headless native
presentation for OS integration tests. The original libcosmic Layer Shell UI,
settings and freedesktop daemon are not replaced by a launcher or applet stub.
No OS provider implementation or user notification data is copied.

The public desktop identity remains `com.clawos.Notifications`; native
crate/binary/App identity remains `cosmic-notifications`. The OS pins the
published product revision and ships native payloads in `claw-os-desktop`.
System76/COSMIC trademarks are not licensed for unrestricted reuse.
