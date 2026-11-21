pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland
import Quickshell.Bluetooth
import Caelestia
import Caelestia.I18n
import Caelestia.State
import qs.components.containers
import qs.services

StyledWindow {
    id: root

    required property StyledWindow bar
    property string page
    property string pinId
    property real pinX
    readonly property var backlight: screen ? Brightness.getMonitorForScreen(screen) : null
    readonly property bool pinMenu: page === "pin"

    name: "claw-top-menu"
    visible: page !== ""
    anchors {
        top: true
        left: root.pinMenu
        right: !root.pinMenu
    }
    margins {
        top: 8
        left: root.pinMenu ? Math.min(Math.max(8, root.pinX), root.screen.width - root.implicitWidth - 8) : 0
        right: root.pinMenu ? 0 : 8
    }
    exclusiveZone: 0
    implicitWidth: Math.min(pinMenu ? 216 : 408, screen.width - 16)
    implicitHeight: Math.max(1, Math.min(body.implicitHeight + 28, screen.height - bar.implicitHeight - 16))
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.OnDemand

    function toggle(name: string): void {
        page = page === name ? "" : name;
    }

    function settings(): void {
        page = "";
        DesktopMenu.launch("com.clawos.Settings");
    }

    HyprlandFocusGrab {
        active: root.visible
        windows: [root, root.bar]
        onCleared: root.page = ""
    }

    Rectangle {
        anchors.fill: parent
        color: Quiet.panel
        border.color: Quiet.line
        radius: 8

        ScrollView {
            id: scroll

            anchors.fill: parent
            anchors.margins: 14
            contentWidth: availableWidth
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            focus: true
            Keys.priority: Keys.BeforeItem
            Keys.onEscapePressed: root.page = ""

            ColumnLayout {
                id: body

                width: scroll.availableWidth
                spacing: 5

                RowLayout {
                    visible: !root.pinMenu
                    Layout.fillWidth: true

                    Text {
                        Layout.fillWidth: true
                        color: Quiet.ink
                        font.pixelSize: 17
                        font.bold: true
                        text: ({
                            control: Tr.tr("Control Center"),
                            notifications: Tr.tr("Notifications"),
                            overview: Tr.tr("Desktop overview"),
                            power: Tr.tr("Power"),
                            logout: Tr.tr("Log out to switch users?")
                        })[root.page] ?? ""
                    }

                    QuietButton {
                        text: "\u00d7"
                        Accessible.name: Tr.tr("Close panel")
                        onClicked: root.page = ""
                    }
                }

                ColumnLayout {
                    visible: root.page === "control"
                    Layout.fillWidth: true
                    spacing: 4

                    SettingRow {
                        title: Tr.tr("Wi-Fi")
                        description: Nmcli.active?.ssid || Tr.tr("Network settings")
                        action: Tr.tr("Settings")
                        onClicked: root.settings()
                    }
                    SettingRow {
                        title: Tr.tr("Bluetooth")
                        description: Bluetooth.defaultAdapter
                            ? (Bluetooth.defaultAdapter.enabled ? Tr.tr("On") : Tr.tr("Off"))
                            : Tr.tr("Bluetooth settings")
                        action: Tr.tr("Settings")
                        onClicked: root.settings()
                    }
                    SettingRow {
                        title: Tr.tr("Do not disturb")
                        description: PersistentState.doNotDisturb ? Tr.tr("On") : Tr.tr("Off")
                        action: PersistentState.doNotDisturb ? Tr.tr("Turn off") : Tr.tr("Turn on")
                        onClicked: PersistentState.doNotDisturb = !PersistentState.doNotDisturb
                    }

                    LevelRow {
                        title: Tr.tr("Volume")
                        available: Audio.sink !== null
                        adjustable: Audio.canSetOutput
                        reading: Audio.volume
                        onChangedByUser: value => Audio.setVolume(value)
                    }
                    LevelRow {
                        title: Tr.tr("Brightness")
                        available: root.backlight?.available ?? false
                        adjustable: root.backlight?.adjustable ?? false
                        reading: root.backlight?.brightness ?? 0
                        onChangedByUser: value => root.backlight?.setBrightness(value)
                    }
                    Separator {}

                    RowLayout {
                        Layout.fillWidth: true

                        QuietButton {
                            text: Tr.tr("Settings")
                            onClicked: root.settings()
                        }
                        QuietButton {
                            text: Tr.tr("Notifications")
                            onClicked: root.page = "notifications"
                        }
                        QuietButton {
                            text: Tr.tr("Power")
                            onClicked: root.page = "power"
                        }
                        Item { Layout.fillWidth: true }
                        QuietButton {
                            text: Quiet.light ? Tr.tr("Dark appearance") : Tr.tr("Light appearance")
                            onClicked: Quiet.toggleAppearance()
                        }
                    }
                }

                ColumnLayout {
                    visible: root.page === "overview"
                    Layout.fillWidth: true

                    Text {
                        color: Quiet.ink
                        font.pixelSize: 25
                        text: Time.format("hh:mm")
                    }
                    Text {
                        color: Quiet.dim
                        text: Time.format("dddd, MMMM d")
                    }
                    Separator {}
                    QuietButton {
                        text: Tr.tr("Settings")
                        onClicked: root.settings()
                    }
                }

                ColumnLayout {
                    visible: root.page === "notifications"
                    Layout.fillWidth: true

                    Text {
                        visible: Notifs.notClosed.length === 0 || Notifs.unavailable
                        text: Notifs.unavailable ? Tr.tr("Notifications unavailable") : Tr.tr("No notifications")
                        color: Quiet.dim
                    }

                    Repeater {
                        model: root.page === "notifications" ? Notifs.notClosed : []

                        delegate: ColumnLayout {
                            id: notification

                            required property var modelData
                            Layout.fillWidth: true

                            SettingRow {
                                title: notification.modelData.summary || notification.modelData.appName
                                description: notification.modelData.body
                                action: Tr.tr("Dismiss")
                                actionEnabled: notification.modelData.confirmed && !notification.modelData.pending
                                onClicked: notification.modelData.close()
                            }
                            Separator {}
                        }
                    }
                }

                ColumnLayout {
                    visible: root.page === "power"
                    Layout.fillWidth: true

                    QuietButton {
                        text: Tr.tr("Lock")
                        onClicked: {
                            root.page = "";
                            ScreenLock.request();
                        }
                    }
                    Repeater {
                        model: [
                            {label: Tr.tr("Sleep"), action: "suspend"},
                            {label: Tr.tr("Restart"), action: "reboot"},
                            {label: Tr.tr("Shut down"), action: "poweroff"}
                        ]
                        QuietButton {
                            required property var modelData

                            text: modelData.label
                            enabled: !Power.busy
                            onClicked: {
                                root.page = "";
                                Power.request(modelData.action);
                            }
                        }
                    }
                    QuietButton {
                        text: Tr.tr("Log out / switch user")
                        onClicked: root.page = "logout"
                    }
                }

                ColumnLayout {
                    visible: root.page === "logout"
                    Layout.fillWidth: true

                    Text {
                        Layout.fillWidth: true
                        color: Quiet.dim
                        wrapMode: Text.WordWrap
                        text: Tr.tr("Save your work first. Logging out closes your apps and returns to the account picker.")
                    }

                    RowLayout {
                        QuietButton {
                            text: Tr.tr("Cancel")
                            onClicked: root.page = "power"
                        }
                        QuietButton {
                            text: Tr.tr("Log out")
                            onClicked: Qt.quit()
                        }
                    }
                }

                QuietButton {
                    visible: root.pinMenu
                    Layout.fillWidth: true
                    text: Quiet.pins.includes(root.pinId) ? Tr.tr("Unpin from top bar") : Tr.tr("Pin to top bar")
                    onClicked: {
                        Quiet.togglePin(root.pinId);
                        root.page = "";
                    }
                }
            }
        }
    }

    component Separator: Rectangle {
        Layout.fillWidth: true
        implicitHeight: 1
        color: Quiet.line
    }

    component SettingRow: RowLayout {
        id: setting

        required property string title
        property string description
        required property string action
        property bool actionEnabled: true
        signal clicked()

        Layout.fillWidth: true

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            Text {
                Layout.fillWidth: true
                text: setting.title
                textFormat: Text.PlainText
                color: Quiet.ink
                elide: Text.ElideRight
            }
            Text {
                Layout.fillWidth: true
                text: setting.description
                textFormat: Text.PlainText
                color: Quiet.dim
                font.pixelSize: 11
                elide: Text.ElideRight
                visible: text.length > 0
            }
        }

        QuietButton {
            text: setting.action
            enabled: setting.actionEnabled
            onClicked: setting.clicked()
        }
    }

    component LevelRow: RowLayout {
        id: level

        required property string title
        required property bool available
        required property bool adjustable
        required property real reading
        signal changedByUser(real value)

        Layout.fillWidth: true

        Text {
            Layout.preferredWidth: 75
            text: level.title
            color: Quiet.ink
            elide: Text.ElideRight
        }

        Slider {
            id: slider

            Layout.fillWidth: true
            enabled: level.adjustable
            live: false
            Accessible.name: level.title
            palette.highlight: Quiet.accent
            palette.base: Quiet.field
            onMoved: level.changedByUser(value)
            Binding {
                target: slider
                property: "value"
                value: level.reading
                when: !slider.pressed
            }
        }

        Text {
            Layout.preferredWidth: 42
            horizontalAlignment: Text.AlignRight
            text: level.available ? `${Math.round(slider.value * 100)}%` : "\u2014"
            color: Quiet.dim
        }
    }
}
