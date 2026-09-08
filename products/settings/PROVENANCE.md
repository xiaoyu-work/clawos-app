# Settings provenance

The complete native workspace in `native/cosmic-settings` was moved from
`xiaoyu-work/claw-os` commit `0323fb58e9e668dc0447bd966830ca1f6c5a4de9`,
formerly `desktop/settings`. Its upstream is
[`pop-os/cosmic-settings`](https://github.com/pop-os/cosmic-settings), recorded
upstream revision `703a934b096b` in the OS provenance table.

All workspace members, subscriptions, pages, translations, resource/configuration
schemas, packaging files and hidden build metadata move together. Original
`LICENSE.md`, Debian copyright and source notices are retained. The root UI is
GPL-3.0-only; member-specific licenses (including MPL-2.0) remain intact;
`native/LICENSE` is the same license for the native staging contract.
System76 trademarks are not relicensed by this move.

The original lock, default pages and renderer features remain intact. Local
toolkit/iced patches resolve through the immutable OS library pin during App
development and the OS's shared toolkit during image builds. The original
protocol/AT-SPI patches and git config-schema dependencies are retained.
No Settings Daemon, compositor, panel service, kernel, model provider or
privileged management implementation has been imported.

The eleven management Apps retain their original independent identities and
permissions. The separate `cosmic-settings` binary retains
`/usr/bin/cosmic-settings`, `com.clawos.Settings` resources and its original
page-discovery/fixed-launch contract, plus four OS-backed permission tools.
Their shared native client, durable policy consent and fixed user-service
activation do not import OS authority into this product. Source relocation does not migrate
credentials, user configuration, device state or provider consent.
