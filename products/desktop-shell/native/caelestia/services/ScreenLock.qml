pragma Singleton

import Quickshell
import Quickshell.Io
import Caelestia
import Caelestia.I18n

Singleton {
    function request(): void {
        if (!effect.running)
            effect.running = true;
    }

    Process {
        id: effect

        command: ["/usr/bin/python3", Quickshell.shellPath("utils/scripts/desktop_lock.py")]
        onExited: exitCode => {
            if (exitCode !== 0)
                Toaster.toast(Tr.tr("Lock not confirmed"), Tr.tr("Yu OS did not confirm the screen lock."), "lock");
        }
    }
}
