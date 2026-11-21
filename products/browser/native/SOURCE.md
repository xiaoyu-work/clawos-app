# Helium source

`helium/` is the complete tracked source tree from
[imputnet/helium](https://github.com/imputnet/helium/tree/f32f2c066787492b9ba112dc1be1ad230b53658a)
at `f32f2c066787492b9ba112dc1be1ad230b53658a`. It contains the Helium
patches, resources, Chromium version and upstream build inputs, not an
expanded Chromium checkout. Preserve its GPL-3.0 and upstream license files.

The Claw OS integration uses the official `helium-bin` Linux package for
both desktop and private rendering. The App package depends on it; it does not
repackage upstream binaries or non-free assets. Claw-specific desktop defaults,
network authority and process isolation remain in Claw OS, and the extension,
MCP tools and presentation remain in this product. The packaged binary is an
upstream build, not a local build of this imported source.
