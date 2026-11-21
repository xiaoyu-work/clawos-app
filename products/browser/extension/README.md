# Yu OS Agent — WebExtension

The user-facing half of `browser-attached`. It lets the user talk to the
system Yu OS Agent in Helium and gives that Agent permission-gated tools for
the user's logged-in browser tabs.

## Layout

| File | Purpose |
|------|---------|
| `manifest.json` | MV3 manifest; the side panel is unavailable in private windows. |
| `background.js` | Service worker. Owns the native messaging port to `com.clawos.browser`. Translates verbs into `chrome.tabs.*` / `chrome.scripting.*` and forwards to `content.js`. |
| `content.js`    | Per-frame DOM helper. Owns the per-page element ref table, executes `query` / `click` / `fill` / `snapshot`. |
| `popup.html` + `popup.js` | Chat side panel with streamed replies, tab selection, approval state, and Stop. |

Click the toolbar button to open the side panel alongside the current page.
The panel talks to the separate `com.clawos.browser_chat` host installed by
Yu OS Desktop. It uses the existing system Agent and Job state; stopping
a reply cancels its Job. Closing the panel does not cancel the Job; reopening
it in the same window reconnects. **Pause tab access** separately disconnects
the browser action bridge until resumed. It does not undo a dispatched action.

Attach the current tab explicitly to share its ID and site origin rather than
its full URL or contents. Read and write permissions still come from `clawd`,
not from opening the panel or selecting a tab.

DOM messages are sent only to frame `0`, and the content script exits if it is
ever injected into a child frame. Element refs therefore cannot collide across
iframes or authorize actions against a different embedded origin. A random
per-document ref nonce also makes refs fail closed after navigation.

Every tab-content request carries an `expected_origin` injected by `clawd`
after exact capability authorization. It includes the scheme, host, and
effective port. `background.js` checks it against the selected tab and
`content.js` checks it again in the page immediately before the DOM action.
Screenshot capture also rejects activation or navigation changes during the
capture interval. Callers cannot supply `allow_secret` or `allow_eval`; the
daemon injects those flags only after spending the corresponding capability.

DOM read operations deliberately omit current values from editable controls.
Responses contain labels, refs, sensitivity classification, and a
`value_present` boolean, but never password, OTP, payment, hidden-token, or
ordinary typed input values.

## Loading

The OS-owned
[`tools/install-browser-agent.sh`](https://github.com/xiaoyu-work/claw-os/blob/main/tools/install-browser-agent.sh)
checks the installed `claw-app-browser` package assets and configures the
extension allowlist and Native Messaging registration. The package owns this
complete directory at `/usr/share/claw/extensions/claw-agent-browser` and
`/usr/lib/cos/claw-browser-host`, which executes the OS-owned transport at
`/usr/lib/cos/browser-native-host.py` with isolated `/usr/bin/python3`.
The matching Agent provides `claw-os-browser-bridge-v1`; this is transport
availability, not an App grant. Independent Browser APT upgrades update the
extension and its launcher together; the OS registration
command never clones App source or copies a second Native Host. It does not
force-install an extension, kill a running browser, or modify browser profiles.
Reload the extension/browser normally after an update.

Load the installed directory unpacked, or this source directory during development:

```
helium --no-default-browser-check
# helium://extensions → Developer mode → Load unpacked
# Installed package: /usr/share/claw/extensions/claw-agent-browser
```

Note the resulting extension ID and put it into
`/etc/chromium/native-messaging-hosts/com.clawos.browser.json`'s
`allowed_origins` array so Helium will start the native host. This is the
upstream-compatible Linux path the Helium binary resolves.
Run the installer with `CLAW_EXT_ID` to register both hosts; for chat,
install the matching Yu OS Desktop package and keep the existing local
Agent bridge available. The chat panel shows an error if it cannot reach it.

## Wire protocol

Same JSON envelope on both NM stdio and the AF_UNIX socket:

```
request:  { id, verb, args }
response: { id, ok: true,  result }
response: { id, ok: false, error }
```

The socket lives at `$XDG_RUNTIME_DIR/claw-browser.sock`, has mode `0600`, and
accepts only a root peer. Sandboxed Apps never receive the socket; they call the
typed `system.browser.control` provider through the private runtime bridge.

See [`claw-os/docs/browser-attached-design.md`](https://github.com/xiaoyu-work/claw-os/blob/main/docs/browser-attached-design.md) for the full architecture diagram and
the capability matrix.
