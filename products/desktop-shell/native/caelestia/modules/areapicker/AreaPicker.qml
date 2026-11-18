import Quickshell
import Caelestia
import Caelestia.I18n
import qs.components.misc
import qs.modules.launcher.services

Scope {
    CustomShortcut {
        name: "screenshot"
        description: "Open Capture"
        onPressed: {
            const entry = DesktopEntries.byId("com.clawos.Screenshot");
            if (entry)
                Apps.launch(entry);
            else
                Toaster.toast(Tr.tr("Capture unavailable"), Tr.tr("The Capture application is not installed."), "error");
        }
    }
}
