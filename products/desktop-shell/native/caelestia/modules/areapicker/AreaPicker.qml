import Quickshell
import qs.components.misc
import qs.services

Scope {
    CustomShortcut {
        name: "screenshot"
        description: "Open Capture"
        onPressed: DesktopMenu.launch("com.yuos.Screenshot")
    }
}
