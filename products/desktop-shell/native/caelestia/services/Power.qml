pragma Singleton
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import Caelestia
import Caelestia.I18n

Singleton {
    id: root

    readonly property bool available: ShellState.controlPower
    readonly property bool busy: effect.running

    function prompt(action: string): string {
        switch (action) {
        case "poweroff": return Tr.tr("Shut down this computer?");
        case "reboot": return Tr.tr("Restart this computer?");
        case "hibernate": return Tr.tr("Hibernate this computer?");
        case "suspend": return Tr.tr("Put this computer to sleep?");
        case "suspend-then-hibernate": return Tr.tr("Put this computer to sleep, then hibernate?");
        default: return "";
        }
    }

    function request(action: string): void {
        if (!available || busy || prompt(action) === "")
            return;
        effect.command = ["/usr/bin/python3", Quickshell.shellPath("utils/scripts/power_control.py"), action];
        effect.running = true;
    }

    Process {
        id: effect

        stdout: StdioCollector { id: reply }
        onExited: exitCode => {
            if (exitCode !== 0 || reply.text.trim() !== "requested")
                Toaster.toast(Tr.tr("Power request not confirmed"), Tr.tr("The OS did not confirm the requested power action."), "error");
        }
    }
}
