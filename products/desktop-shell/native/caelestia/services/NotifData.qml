pragma ComponentBehavior: Bound

import QtQuick
import Quickshell.Services.Notifications
import Caelestia.Config
import Caelestia.I18n

QtObject {
    id: notif

    required property double handle
    required property string token
    property bool popup
    property bool closed
    property bool confirmed
    property bool pending
    property bool ephemeral
    property var locks: new Set()
    property string summary
    property string body
    property string appIcon
    property string appName
    readonly property string image: ""
    readonly property var hints: ({})
    property int expireTimeout: -1
    property int urgency: NotificationUrgency.Normal
    readonly property bool resident: false
    readonly property bool hasActionIcons: false
    readonly property list<var> actions: [{
        identifier: "default", text: Tr.tr("Acknowledge"),
        invoke: () => Notifs.feedback(notif, "activated", { action: "default" })
    }]

    readonly property date time: new Date()
    property int ageMins: 0
    readonly property string timeStr: {
        if (ageMins < 1)
            return Tr.tr("now");
        const hours = Math.floor(ageMins / 60);
        const days = Math.floor(hours / 24);
        if (days > 0)
            return Tr.trCtx("%1d", "abbreviated notification age, days").arg(days);
        if (hours > 0)
            return Tr.trCtx("%1h", "abbreviated notification age, hours").arg(hours);
        return Tr.trCtx("%1m", "abbreviated notification age, minutes").arg(ageMins);
    }

    readonly property Timer timeStrTimer: Timer {
        running: !notif.closed
        repeat: true
        interval: 30000
        onTriggered: notif.ageMins = Math.floor((Date.now() - notif.time.getTime()) / 60000)
    }

    readonly property Timer timer: Timer {
        running: notif.popup && notif.expireTimeout !== 0
        interval: notif.expireTimeout > 0 ? notif.expireTimeout : GlobalConfig.notifs.defaultExpireTimeout
        onTriggered: notif.expire()
    }

    function expire(): void {
        popup = false;
        if (ephemeral)
            Notifs.feedback(this, "closed", { reason: "expired" });
    }

    onPopupChanged: {
        if (!popup && ephemeral && confirmed && !pending && !closed)
            Qt.callLater(expire);
    }

    function lock(item: Item): void {
        locks.add(item);
    }

    function unlock(item: Item): void {
        locks.delete(item);
        if (closed)
            retire();
    }

    function close(): void {
        Notifs.feedback(this, "closed", { reason: "dismissed" });
    }

    function retire(): void {
        popup = false;
        closed = true;
        if (locks.size === 0 && Notifs.list.includes(this)) {
            Notifs.list = Notifs.list.filter(n => n !== this);
            destroy();
        }
    }
}
