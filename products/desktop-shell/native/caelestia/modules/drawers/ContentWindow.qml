pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland
import qs.components
import qs.components.containers
import qs.services

StyledWindow {
    id: root

    required property real topInset
    required property StyledWindow topBar
    readonly property alias interactionWrapper: panels
    readonly property ScreenState screenState: ShellState.forScreen(screen)
    readonly property bool keyboardMenu: screenState.session || screenState.sidebar || screenState.dashboard

    name: "drawers"
    anchors {
        top: true
        bottom: true
        left: true
        right: true
    }
    WlrLayershell.exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Top
    WlrLayershell.keyboardFocus: keyboardMenu ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None

    mask: Region {
        Region { item: panels.notifications.visible ? panels.notifications : null }
        Region { item: panels.dashboard.visible ? panels.dashboard : null }
        Region { item: panels.session.visible ? panels.sessionWrapper : null }
        Region { item: panels.sidebar.visible ? panels.sidebar : null }
        Region { item: panels.osd.visible ? panels.osdWrapper : null }
        Region { item: panels.utilities.visible ? panels.utilities : null }
        Region { item: panels.popouts.visible ? panels.popoutsWrapper : null }
    }

    HyprlandFocusGrab {
        active: root.keyboardMenu
        windows: [root, root.topBar]
        onCleared: {
            root.screenState.session = false;
            root.screenState.sidebar = false;
            root.screenState.dashboard = false;
        }
    }

    Panels {
        id: panels

        screen: root.screen
        screenState: root.screenState
        borderThickness: 8
        topInset: root.topInset

        Surface { panel: panels.dashboard }
        Surface { panel: panels.sessionWrapper; visible: panels.session.visible }
        Surface { panel: panels.sidebar }
        Surface { panel: panels.osdWrapper; visible: panels.osd.visible }
        Surface { panel: panels.notifications }
        Surface { panel: panels.utilities }
        Surface { panel: panels.popoutsWrapper; visible: panels.popouts.visible }
    }

    Rectangle {
        id: dockLabel

        // Keep the label out of the input mask so it cannot intercept clicks.
        visible: root.topBar.dockTooltip !== ""
        x: Math.max(6, Math.min(parent.width - width - 6, Math.round(root.topBar.dockTooltipX - width / 2)))
        y: root.topInset + 6
        width: Math.min(label.implicitWidth + 16, 176, Math.max(0, parent.width - 12))
        height: label.implicitHeight + 8
        radius: 5
        color: Quiet.panel
        border.color: Quiet.line

        Text {
            id: label

            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            text: root.topBar.dockTooltip
            textFormat: Text.PlainText
            color: Quiet.ink
            font.pixelSize: 12
            maximumLineCount: 1
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }

    ShellState.ComponentRef {
        screen: root.screen
        slot: "rootWindow"
        component: root
    }

    ShellState.ComponentRef {
        screen: root.screen
        slot: "interactionWrapper"
        component: panels
    }

    ShellState.ComponentRef {
        screen: root.screen
        slot: "bar"
        component: root.topBar
    }

    ShellState.ComponentRef {
        screen: root.screen
        slot: "panels"
        component: panels
    }

    component Surface: Rectangle {
        required property Item panel

        x: panel.x
        y: panel.y
        width: panel.width
        height: panel.height
        z: -1
        visible: panel.visible
        color: Quiet.panel
        radius: 8
    }
}
