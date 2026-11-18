import QtQuick
import QtQuick.Layouts
import Caelestia.Config
import Caelestia.I18n
import qs.components
import qs.services

ColumnLayout {
    id: root

    required property var client

    anchors.fill: parent
    spacing: Tokens.spacing.small

    Label {
        Layout.topMargin: Tokens.padding.extraLargeIncreased

        text: root.client?.title ?? Tr.tr("No active client")
        wrapMode: Text.WrapAtWordBoundaryOrAnywhere

        font: Tokens.font.body.builders.large.weight(Font.Medium).build()
    }

    Label {
        text: root.client?.lastIpcObject.class ?? Tr.tr("No active client")
        color: Colours.palette.m3tertiary

        font: Tokens.font.body.large
    }

    StyledRect {
        Layout.fillWidth: true
        Layout.preferredHeight: 1
        Layout.leftMargin: Tokens.padding.extraLargeIncreased
        Layout.rightMargin: Tokens.padding.extraLargeIncreased
        Layout.topMargin: Tokens.spacing.medium
        Layout.bottomMargin: Tokens.spacing.largeIncreased

        color: Colours.palette.m3secondary
    }

    Detail {
        icon: "location_searching"
        // TRANSLATORS: %1/%2 = x and y position in pixels
        text: Tr.tr("Position: %1, %2").arg(root.client?.lastIpcObject.at[0] ?? -1).arg(root.client?.lastIpcObject.at[1] ?? -1)
    }

    Detail {
        icon: "resize"
        // TRANSLATORS: %1/%2 = width and height in pixels; the x is a multiplication sign
        text: Tr.tr("Size: %1 x %2").arg(root.client?.lastIpcObject.size[0] ?? -1).arg(root.client?.lastIpcObject.size[1] ?? -1)
        color: Colours.palette.m3tertiary
    }

    Detail {
        icon: "workspaces"
        // TRANSLATORS: %1 = workspace name, %2 = workspace id
        text: Tr.tr("Workspace: %1").arg(root.client?.workspace?.name ?? "-")
        color: Colours.palette.m3secondary
    }

    Detail {
        icon: "desktop_windows"
        text: {
            const mon = root.client?.monitor;
            if (mon)
                return Tr.tr("Monitor: %1").arg(mon.name);
            return Tr.tr("Monitor: unknown");
        }
    }

    Detail {
        icon: "picture_in_picture_center"
        text: root.client?.lastIpcObject.floating ? Tr.tr("Floating: yes") : Tr.tr("Floating: no")
        color: Colours.palette.m3secondary
    }

    Detail {
        icon: "gradient"
        text: root.client?.lastIpcObject.xwayland ? Tr.tr("Xwayland: yes") : Tr.tr("Xwayland: no")
    }

    Detail {
        icon: "keep"
        text: root.client?.lastIpcObject.pinned ? Tr.tr("Pinned: yes") : Tr.tr("Pinned: no")
        color: Colours.palette.m3secondary
    }

    Detail {
        icon: "fullscreen"
        text: {
            const fs = root.client?.lastIpcObject.fullscreen;
            if (fs === 0)
                return Tr.tr("Fullscreen state: off");
            if (fs === 1)
                return Tr.tr("Fullscreen state: maximised");
            if (fs !== undefined)
                return Tr.tr("Fullscreen state: on");
            return Tr.tr("Fullscreen state: unknown");
        }
        color: Colours.palette.m3tertiary
    }

    Item {
        Layout.fillHeight: true
    }

    component Detail: RowLayout {
        id: detail

        required property string icon
        required property string text
        property alias color: icon.color

        Layout.leftMargin: Tokens.padding.large
        Layout.rightMargin: Tokens.padding.large
        Layout.fillWidth: true

        spacing: Tokens.spacing.medium

        MaterialIcon {
            id: icon

            Layout.alignment: Qt.AlignVCenter
            text: detail.icon
        }

        StyledText {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter

            text: detail.text
            elide: Text.ElideRight
            font: Tokens.font.body.medium
        }
    }

    component Label: StyledText {
        Layout.leftMargin: Tokens.padding.large
        Layout.rightMargin: Tokens.padding.large
        Layout.fillWidth: true
        elide: Text.ElideRight
        horizontalAlignment: Text.AlignHCenter
        animate: true
    }
}
