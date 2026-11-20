import QtQuick
import QtQuick.Controls.Basic
import qs.services

Button {
    id: root

    padding: 8
    hoverEnabled: true
    font.pixelSize: 13

    contentItem: Text {
        text: root.text
        color: root.enabled ? Quiet.ink : Quiet.dim
        textFormat: Text.PlainText
        font: root.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        implicitHeight: 32
        radius: 5
        color: root.down || root.checked ? Quiet.selected
            : root.hovered || root.visualFocus ? Quiet.field : "transparent"
        border.color: root.visualFocus ? Quiet.accent : "transparent"
    }
}
