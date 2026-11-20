pragma Singleton
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import Caelestia
import Caelestia.I18n

Singleton {
    id: root

    readonly property bool busy: effect.running

    function supports(action: string): bool {
        return ["poweroff", "reboot", "hibernate", "suspend", "suspend-then-hibernate"].includes(action);
    }

    function request(action: string): void {
        if (busy || !supports(action))
            return;
        effect.submitted = false;
        effect.failure = "";
        effect.command = ["/usr/bin/python3", Quickshell.shellPath("utils/scripts/desktop_review.py"), "power", action];
        effect.running = true;
    }

    Process {
        id: effect

        property bool submitted: false
        property string failure

        stdout: SplitParser {
            onRead: line => {
                try {
                    const message = JSON.parse(line);
                    if (message?.submitted === true)
                        effect.submitted = true;
                    else if (typeof message?.error === "string")
                        effect.failure = message.error.slice(0, 1024);
                } catch (_error) {
                    effect.failure = Tr.tr("The power service returned an invalid response.");
                }
            }
        }

        onExited: exitCode => {
            if (exitCode !== 0 || !submitted)
                Toaster.toast(Tr.tr("Power request not confirmed"), failure || Tr.tr("The OS did not confirm the requested power action."), "error");
        }
    }
}
