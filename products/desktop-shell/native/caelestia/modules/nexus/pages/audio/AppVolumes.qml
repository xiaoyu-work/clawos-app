pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import Quickshell
import Caelestia.Config
import Caelestia.I18n
import qs.components
import qs.services
import qs.utils
import qs.modules.nexus.common

PageBase {
    id: root

    title: Tr.tr("Audio streams")
    isSubPage: true

    ColumnLayout {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        width: root.cappedWidth
        spacing: Tokens.spacing.extraSmall / 2

        StyledText {
            Layout.fillWidth: true
            Layout.leftMargin: Tokens.padding.small
            Layout.bottomMargin: Tokens.spacing.medium
            text: Tr.tr("Audio streams reported by the OS.")
            color: Colours.palette.m3outline
            font: Tokens.font.body.small
            wrapMode: Text.WordWrap
        }

        ItemList {
            id: streamList

            first: true
            last: true
            showList: true
            placeholderIcon: "music_off"
            placeholderText: Tr.tr("No apps playing audio")
            color: list.count === 0 ? Colours.tPalette.m3surfaceContainer : "transparent"
            list.spacing: Tokens.spacing.extraSmall / 2

            model: ScriptModel {
                values: [...Audio.streams]
            }

            delegate: StyledText {
                id: stream

                required property var modelData

                anchors.left: streamList.list.contentItem.left
                anchors.right: streamList.list.contentItem.right
                padding: Tokens.padding.medium
                text: Audio.getStreamName(stream.modelData)
                elide: Text.ElideRight
            }
        }
    }
}
