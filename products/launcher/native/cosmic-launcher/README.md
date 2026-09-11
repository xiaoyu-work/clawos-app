# Cosmic Launcher

Layer Shell frontend for https://github.com/pop-os/launcher. Currently the underlying protocol being used in the plugin for managing toplevels in wayland is defined [here](https://github.com/pop-os/cosmic-protocols/blob/main/unstable/cosmic-toplevel-info-unstable-v1.xml) but it will be switched to use [wlr-foreign-toplevel-management](https://wayland.app/protocols/wlr-foreign-toplevel-management-unstable-v1) when it is ready.

# Building

Cosmic Launcher is set up to build a deb and a Nix flake, but it can be built using just.

Some Build Dependencies:
```
  cargo,
  just,
  intltool,
  appstream-util,
  desktop-file-utils,
  libxkbcommon-dev,
  pkg-config,
  desktop-file-utils,
```

## Build Commands

For a typical install from source, use `just` followed with `sudo just install`.
```sh
just
sudo just install
```

If you are packaging, run `just vendor` outside of your build chroot, then use `just build-vendored` inside the build-chroot. Then you can specify a custom root directory and prefix.
```sh
# Outside build chroot
just clean-dist
just vendor

# Inside build chroot
just build-vendored
sudo just rootdir=debian/cosmic-launcher prefix=/usr install
```

# Translators

Translation files may be found in the i18n directory. New translations may copy the English (en) localization of the project and rename `en` to the desired [ISO 639-1 language code](https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes). Translations may be submitted through GitHub as an issue or pull request. Submissions by email or other means are also acceptable; with the preferred name and email to associate with the changes.

# Debugging & Profiling

## Profiling async tasks with tokio-console

To debug issues with asynchronous code, install [tokio-console](https://github.com/tokio-rs/console) and run it within a separate terminal. Then kill the **cosmic-launcher** process a couple times in quick succession to prevent **cosmic-session** from spawning it again. Then you can start **cosmic-launcher** with **tokio-console** support either by running `just tokio-console` from this repository to test code changes, or `env TOKIO_CONSOLE=1 cosmic-launcher` to enable it with the installed version of **cosmic-launcher**.

## Claw OS MCP service

The App Host starts `/usr/bin/cosmic-launcher` with `COS_MCP_SERVER=1`.
The product's `apps/cosmic-launcher/app.json` owns its four-tool contract.
The native executable embeds the canonical product backend from
`apps/launcher/main.py` and `mcp_server.py` at build time. MCP mode replaces
the process with the fixed isolated system Python interpreter and serves
through the versioned OS Python SDK. It does not load another installed
App's implementation or call its CLI/MCP interface.

Only fixed OS SDK/runtime/shared-library directories are added to Python's
isolated import path. The authenticated host transport, sandbox, identity
and data directory survive process replacement. Policy checks and typed
`cos __desktop launch` requests remain OS-owned. Arbitrary command-line text
and file URIs are rejected; canonical local files additionally require exact
read authority, which the native descriptor does not automatically grant.

From the application repository root:

```sh
python3 tools/test.py launcher
python3 tools/native_build.py launcher test
python3 tools/native_build.py launcher build
```

These commands stage complete source and shared backend inputs under
`build/launcher-native` against immutable OS dependencies. Use its justfile
for resource installation after building. The on-screen UI still uses the
OS launcher service; this move does not unify that service's catalog/history
with isolated MCP data or change the UI.

## Native GUI arguments

After MCP dispatch, SDK GUI mode removes one exact leading `--gui` Host selector
before the existing native Clap parser. The program name and all other
arguments remain intact; direct CLI mode does not accept a new `--gui` option.
For example, `input -- --gui` still passes the literal input `--gui`.
Help/version, subcommands and single-instance serialization are unchanged.
Parser regressions live in `test/unit/argparse.rs`; argument adaptation grants
no desktop, catalog, history or resource access.