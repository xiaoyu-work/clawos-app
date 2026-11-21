pragma Singleton
pragma ComponentBehavior: Bound

import Quickshell
import Quickshell.Io
import Caelestia
import Caelestia.I18n

Singleton {
    readonly property string files: "com.yuos.Files"
    readonly property string launcher: "com.yuos.Launcher"
    readonly property string agent: "com.yuos.Agent"

    function launch(desktopId: string): void {
        submit("launch", desktopId);
    }

    function activate(desktopId: string): void {
        submit("activate", desktopId);
    }

    function submit(action: string, desktopId: string): void {
        if (effect.running)
            return;
        effect.command = ["/usr/bin/python3", Quickshell.shellPath("utils/scripts/desktop_review.py"), action, desktopId];
        effect.running = true;
    }

    Process {
        id: effect

        stdout: StdioCollector {
            id: result
        }

        onExited: exitCode => {
            if (exitCode !== 0) {
                let message = Tr.tr("Yu OS did not confirm opening the application.");
                if (result.text.trim()) {
                    try {
                        message = JSON.parse(result.text).error || message;
                    } catch (_) {}
                }
                Toaster.toast(Tr.tr("Application did not open"), message, "error");
            }
        }
    }
}
