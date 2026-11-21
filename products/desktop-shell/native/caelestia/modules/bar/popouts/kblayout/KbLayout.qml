import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Caelestia.Config
import Caelestia.I18n
import qs.components
import qs.services

ColumnLayout {
    width: Tokens.sizes.bar.kbLayoutWidth
    spacing: Tokens.spacing.small

    StyledText {
        Layout.fillWidth: true
        text: Hypr.kbLayoutFull || Tr.tr("No active keyboard layout")
        wrapMode: Text.Wrap
    }

    Button {
        readonly property DesktopEntry settings: DesktopEntries.byId("com.yuos.Settings")

        text: Tr.tr("Open Settings")
        enabled: !!settings
        onClicked: DesktopMenu.launch(settings.id)
    }
}
