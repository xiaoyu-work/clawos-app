# Files provenance

The complete native fork was moved from `desktop/files` at OS commit
`3caf1100ee80e87abe9bb190e4be654a03bb2f9a`. Its upstream origin is
[`pop-os/cosmic-files`](https://github.com/pop-os/cosmic-files), revision
`accb9fd41866`, licensed GPL-3.0-only. Native source, resources, translations,
Debian inputs, library, `cosmic-files` and `cosmic-files-applet` remain together;
the original LICENSE and copyright notices are preserved.

The checked-in Cargo.lock and toolkit patches retain the existing native
dependency graph. Only relative shared-library paths change for generated
build layouts. Editor/Terminal/portal file-chooser dependencies remain their
own pinned library dependencies, not product invocations.

Upstream test bodies accidentally excluded by the former `/test/` ignore rule
were recovered verbatim from the parent of OS test-extraction commit
`4bf7dedbb`. Files bridge regressions and authenticated process coverage are
maintained here. Filesystem/Recoll business sources and the extracted shared
document parser retain the repository's Apache-2.0 terms. The Document App
imports the staged parser library; no second reader implementation or App call
is required. OS policy, snapshots, SDK/runtime and Recoll index service remain
outside this product.
