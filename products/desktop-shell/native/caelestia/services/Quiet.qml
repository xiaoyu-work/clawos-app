pragma Singleton
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import Caelestia
import Caelestia.I18n

Singleton {
    id: root

    readonly property bool light: preferences.appearance === "light"
        || (preferences.appearance !== "dark" && Colours.light)
    readonly property color panel: light ? "#f8f7f8f3" : "#f8192522"
    readonly property color ink: light ? "#25352e" : "#f6f7f5"
    readonly property color dim: light ? "#516159" : "#c7d0cd"
    readonly property color line: light ? "#d4dcd2" : "#33d7e3dd"
    readonly property color field: light ? "#e9eee6" : "#13d4dfdc"
    readonly property color selected: light ? "#dce8df" : "#23d4dfdc"
    readonly property color accent: light ? "#2a614b" : "#b0e1ce"

    readonly property list<string> pins: {
        const valid = preferences.pins.filter(id => /^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$/.test(id));
        const ordered = [...new Set([...valid, DesktopMenu.launcher])];
        return ordered.length <= 24 ? ordered : [DesktopMenu.launcher, ...ordered.filter(id => id !== DesktopMenu.launcher).slice(0, 23)];
    }
    readonly property var byStartupClass: new Map(DesktopEntries.applications.values
        .filter(entry => entry.startupClass)
        .map(entry => [entry.startupClass, entry]))

    readonly property var dock: {
        const windows = new Map();
        for (const window of Hypr.toplevels.values) {
            const app = window.lastIpcObject.class;
            if (!app || app === DesktopMenu.agent)
                continue;
            const id = DesktopEntries.byId(app)?.id ?? byStartupClass.get(app)?.id
                ?? (pins.includes(app) ? app : null);
            if (id && (!windows.has(id) || window.active))
                windows.set(id, window);
        }
        return [...new Set([...pins, ...windows.keys()])].map(id => ({
            id, window: windows.get(id) ?? null,
            running: windows.has(id) || (id === DesktopMenu.launcher && Hypr.desktop.launcherRunning === true)
        })).filter(row => row.window || row.id === DesktopMenu.files
            || row.id === DesktopMenu.launcher || DesktopEntries.byId(row.id));
    }

    function title(desktopId: string): string {
        const entry = DesktopEntries.byId(desktopId);
        if (entry)
            return entry.name;
        if (desktopId === DesktopMenu.launcher)
            return Tr.tr("Claw Launcher");
        if (desktopId === DesktopMenu.files)
            return Tr.tr("Files");
        return desktopId;
    }

    function icon(desktopId: string): url {
        const name = DesktopEntries.byId(desktopId)?.icon ?? desktopId;
        return Quickshell.iconPath(name, "application-x-executable");
    }

    function activate(row: var): void {
        if (row.window)
            Hypr.act("focus", row.window.identifier, "");
        else if (!row.running)
            DesktopMenu.launch(row.id);
    }

    function togglePin(id: string): void {
        if (id === DesktopMenu.launcher)
            return;
        if (pins.includes(id))
            preferences.pins = pins.filter(pin => pin !== id);
        else if (pins.length < 24 && (DesktopEntries.byId(id) || dock.some(row => row.id === id)))
            preferences.pins = [...pins, id];
    }

    function toggleAppearance(): void {
        setAppearance(!light);
    }

    function setAppearance(light: bool): void {
        preferences.appearance = light ? "light" : "dark";
    }

    FileView {
        id: file

        readonly property string directory: Quickshell.env("COS_DATA_DIR") || ""
        path: directory ? `${directory}/quiet-desktop.json` : ""
        onAdapterUpdated: {
            if (directory)
                writeAdapter();
        }
        onSaveFailed: Toaster.toast(Tr.tr("Desktop preferences not saved"),
            Tr.tr("Your changes apply for this session only."), "error")

        JsonAdapter {
            id: preferences

            property list<string> pins: [DesktopMenu.files, DesktopMenu.launcher]
            property string appearance: ""
        }
    }
}
