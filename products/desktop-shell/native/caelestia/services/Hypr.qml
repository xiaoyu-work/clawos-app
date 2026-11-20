pragma Singleton
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import Caelestia
import Caelestia.I18n

Singleton {
    id: root

    property var desktop: ({ windows: [], workspaces: [], outputs: [], keyboard: null, runningApps: [] })
    readonly property var toplevels: ({ values: desktop.windows })
    readonly property var workspaces: ({ values: desktop.workspaces })
    readonly property var monitors: ({ values: desktop.outputs })
    readonly property var focusedMonitor: desktop.outputs.find(output => output.focused) ?? null
    readonly property var focusedWorkspace: focusedMonitor?.activeWorkspace ?? null
    readonly property var activeToplevel: desktop.windows.find(window => window.active) ?? null
    readonly property int activeWsId: Math.max(1, focusedWorkspace?.id ?? 1)
    readonly property bool capsLock: desktop.keyboard?.caps_lock ?? false
    readonly property bool numLock: desktop.keyboard?.num_lock ?? false
    readonly property string kbLayoutFull: desktop.keyboard?.active_name ?? ""
    readonly property string kbLayout: desktop.keyboard?.layout ?? ""
    readonly property string defaultKbLayout: desktop.keyboard?.default_layout ?? ""

    function installState(state: var): void {
        const outputs = state.outputs.map(output => ({
            id: output.id, name: output.name, focused: output.focused,
            activeWorkspace: null, lastIpcObject: { specialWorkspace: { id: 0, name: "" } }
        }));
        const workspaces = state.workspaces.map((ws, index) => ({
            id: ws.number ?? -(index + 1),
            name: ws.selector.startsWith("special:") ? ws.selector : ws.name,
            selector: ws.selector,
            urgent: ws.urgent,
            monitor: outputs.find(output => output.id === ws.monitor) ?? null,
            toplevels: { values: [] }
        }));
        const windows = state.windows.map(window => {
            const geometry = window.geometry[0];
            const entry = {
                identifier: window.identifier,
                title: window.title,
                active: window.states.includes("activated"),
                workspace: workspaces.find(ws => ws.selector === window.workspace) ?? null,
                monitor: outputs.find(output => output.id === window.monitor) ?? null,
                lastIpcObject: {
                    class: window.app_id, mapped: true, floating: window.floating, xwayland: window.xwayland,
                    pinned: window.states.includes("sticky"),
                    fullscreen: window.states.includes("fullscreen") ? 2 : window.states.includes("maximized") ? 1 : 0,
                    at: [geometry?.x ?? 0, geometry?.y ?? 0],
                    size: [geometry?.width ?? 0, geometry?.height ?? 0]
                }
            };
            entry.workspace?.toplevels.values.push(entry);
            return entry;
        });
        outputs.forEach((output, index) => {
            const source = state.outputs[index];
            output.activeWorkspace = workspaces.find(ws => ws.selector === source.workspace) ?? null;
            const special = workspaces.find(ws => ws.selector === source.special);
            if (special)
                output.lastIpcObject.specialWorkspace = special;
        });
        workspaces.sort((a, b) => a.id - b.id);
        desktop = { windows, workspaces, outputs, keyboard: state.keyboard,
            runningApps: state.running_apps };
    }

    function focusWorkspace(workspace: var): void {
        act("focus-workspace", "", String(workspace));
    }

    function toggleSpecial(name: string): void {
        act("toggle-special", "", `special:${name}`);
    }

    function act(action: string, identifier: string, workspace: string): void {
        if (effect.pending)
            return;
        const args = ["/usr/bin/python3", Quickshell.shellPath("utils/scripts/desktop_control.py"), action];
        if (identifier)
            args.push("--identifier", identifier);
        if (workspace)
            args.push("--workspace", workspace);
        effect.pending = true;
        effect.command = args;
        effect.running = true;
    }

    function monitorNames(): list<string> {
        return desktop.outputs.map(output => output.name);
    }

    function monitorFor(screen: ShellScreen): var {
        return desktop.outputs.find(output => output.name === screen?.name) ?? null;
    }

    function trimWsName(name: string): string {
        return name.startsWith("special:") ? name.slice("special:".length) : name;
    }

    function toplevelsForWs(ws: int, ignoredTags = []): list<var> {
        return (desktop.workspaces.find(workspace => workspace.id === ws)?.toplevels.values ?? [])
            .filter(toplevel => !isToplevelIgnored(toplevel, ignoredTags));
    }

    function isToplevelIgnored(toplevel: var, ignoredTags = []): bool {
        return !toplevel?.lastIpcObject.class
            || (toplevel.lastIpcObject.tags ?? []).some(tag => ignoredTags.includes(tag.replace(/\*$/, "")));
    }

    Process {
        running: true
        command: ["/usr/local/bin/cos", "__desktop-events"]
        stdout: SplitParser {
            onRead: line => root.installState(JSON.parse(line))
        }
        onExited: {
            root.desktop = { windows: [], workspaces: [], outputs: [], keyboard: null, runningApps: [] };
            console.warn("Desktop state connection closed");
        }
    }

    Process {
        id: effect

        property bool pending: false
        stdout: StdioCollector { id: outcome }
        onExited: exitCode => {
            pending = false;
            if (exitCode !== 0 || JSON.parse(outcome.text).result?.action_applied !== true)
                Toaster.toast(Tr.tr("Desktop action failed"), Tr.tr("The OS did not confirm the requested action."), "error");
        }
        onRunningChanged: {
            if (pending && !running) {
                pending = false;
                Toaster.toast(Tr.tr("Desktop action failed"), Tr.tr("The OS client could not be started."), "error");
            }
        }
    }
}
