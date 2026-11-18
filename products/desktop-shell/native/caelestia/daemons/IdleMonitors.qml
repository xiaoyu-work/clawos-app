pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Wayland
import Quickshell.Services.UPower
import Caelestia.Config
import qs.services

Scope {
    id: root

    readonly property bool hasPlayer: Players.list.some(p => p.isPlaying)
    readonly property bool isCharging: !UPower.onBattery
    readonly property bool enabled: {
        if (GlobalConfig.general.idle.inhibitWhenAudio && hasPlayer)
            return false;
        if (GlobalConfig.general.idle.inhibitWhenCharging && isCharging)
            return false;
        return true;
    }

    function handleIdleAction(action: var): void {
        if (!action)
            return;

        if (action === "lock")
            ScreenLock.request();
    }

    Variants {
        model: GlobalConfig.general.idle.timeouts.values

        IdleMonitor {
            required property var modelData

            enabled: {
                if (!root.enabled || !(modelData.enabled ?? true))
                    return false;
                if (modelData.inhibitWhenAudio && root.hasPlayer)
                    return false;
                if (modelData.inhibitWhenCharging && root.isCharging)
                    return false;
                return true;
            }
            timeout: modelData.timeout
            respectInhibitors: modelData.respectInhibitors ?? true
            onIsIdleChanged: root.handleIdleAction(isIdle ? modelData.idleAction : modelData.returnAction)
        }
    }
}
