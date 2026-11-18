pragma Singleton
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import Caelestia
import Caelestia.Config
import Caelestia.I18n
import Caelestia.State
import qs.components.misc

Singleton {
    id: root

    property list<NotifData> list: []
    readonly property list<NotifData> notClosed: list.filter(n => !n.closed)
    readonly property list<NotifData> popups: list.filter(n => n.popup)
    property list<var> events: []
    property var exchange: null
    property bool unavailable: false
    property bool applyingPreferences: false

    function hasFullscreen(): bool {
        return Hypr.monitors.values.some(m => m.activeWorkspace?.toplevels.values.some(t => t.lastIpcObject.fullscreen > 1));
    }

    function enqueue(event: var, next = false): void {
        if (unavailable)
            return;
        events = next ? [event, ...events] : [...events, event];
        Qt.callLater(pump);
    }

    function feedback(n: NotifData, kind: string, fields: var): void {
        if (!n.confirmed || n.pending || n.closed || unavailable)
            return;
        n.pending = true;
        enqueue(Object.assign({ kind, handle: n.handle, token: n.token }, fields));
    }

    function preferences(requestId: var, next = false): void {
        enqueue({
            kind: "preferences",
            request_id: requestId,
            preferences: { version: 1, muted: PersistentState.doNotDisturb }
        }, next);
    }

    function pump(): void {
        if (unavailable || exchange !== null)
            return;
        const event = events[0] ?? null;
        events = events.slice(1);
        exchange = { event };
        client.stdinEnabled = true;
        client.running = true;
    }

    function failed(): void {
        exchange = null;
        events = [];
        unavailable = true;
        Toaster.toast(Tr.tr("Notifications unavailable"), Tr.tr("The OS notification service did not confirm the exchange."), "error");
    }

    function accept(reply: var): void {
        const sent = exchange.event;
        exchange = null;
        if (sent && sent.handle) {
            const entry = list.find(n => n.handle === sent.handle && n.token === sent.token);
            if (entry && sent.kind === "presented") {
                entry.confirmed = true;
                if (entry.ephemeral && !entry.popup)
                    entry.expire();
            } else if (entry && sent.kind === "closed") {
                entry.retire();
            }
        }

        const command = reply.command;
        if (!command)
            return;
        if (command.kind === "preferences") {
            applyingPreferences = true;
            PersistentState.doNotDisturb = command.muted;
            applyingPreferences = false;
            preferences(command.request_id, true);
            return;
        }
        const n = list.find(entry => entry.handle === command.handle && entry.token === command.token);
        if (command.kind === "present" && !n) {
            const popup = !PersistentState.doNotDisturb && !ShellState.anySidebarOpen()
                && (GlobalConfig.notifs.fullscreen !== NotifsFullscreen.Off || !hasFullscreen());
            const entry = notification.createObject(root, {
                handle: command.handle,
                token: command.token,
                appName: command.app_name,
                appIcon: /^[A-Za-z0-9._-]{1,128}$/.test(command.icon) ? command.icon : "",
                summary: command.summary,
                body: command.body,
                urgency: command.urgency,
                expireTimeout: command.expire_ms,
                ephemeral: command.transient,
                popup
            });
            list = [entry, ...list];
            enqueue({
                kind: "presented", handle: entry.handle, token: entry.token,
                card: entry.ephemeral ? null : JSON.stringify({
                    version: 1, id: entry.handle, source_label: Array.from(entry.appName).slice(0, 256).join(""),
                    title: Array.from(entry.summary).slice(0, 2048).join(""),
                    body: [{ text: Array.from(entry.body).slice(0, 16384).join("") }],
                    activation: "default", icon: null, group_icon: null
                })
            }, true);
        } else if (command.kind === "close" || command.kind === "dismiss") {
            if (n) {
                n.pending = true;
                n.popup = false;
            }
            events = events.filter(event => event.handle !== command.handle || event.token !== command.token);
            enqueue({
                kind: "closed", handle: command.handle, token: command.token,
                reason: command.kind === "dismiss" ? "dismissed" : "closed"
            }, true);
        } else if (command.kind === "activate" && n && !n.pending) {
            feedback(n, "activated", { action: command.action });
        }
    }

    function clear(): void {
        notClosed.forEach(n => n.close());
    }

    Timer {
        running: !root.unavailable
        repeat: true
        interval: 1000
        onTriggered: root.pump()
    }

    Process {
        id: client

        command: ["/usr/bin/python3", Quickshell.shellPath("utils/scripts/notification_exchange.py")]
        stdout: StdioCollector { id: output }

        onStarted: {
            write(JSON.stringify(root.exchange));
            stdinEnabled = false;
        }
        onExited: exitCode => {
            if (exitCode !== 0) {
                root.failed();
                return;
            }
            try {
                const reply = JSON.parse(output.text);
                if (reply.version !== 1)
                    throw new Error("Unsupported notification presentation version");
                root.accept(reply);
            } catch (error) {
                root.failed();
            }
        }
        onRunningChanged: {
            if (!running && root.exchange !== null)
                root.failed();
        }
    }

    Connections {
        target: PersistentState

        function onDoNotDisturbChanged(): void {
            if (!root.applyingPreferences)
                root.preferences(null);
        }
    }

    CustomShortcut {
        name: "clearNotifs"
        description: "Clear all notifications"
        onPressed: root.clear()
    }

    CustomShortcut {
        name: "toggleDnd"
        description: "Toggle do not disturb"
        onPressed: PersistentState.doNotDisturb = !PersistentState.doNotDisturb
    }

    Component { id: notification; NotifData {} }

    Component.onCompleted: preferences(null)
}
