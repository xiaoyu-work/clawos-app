import QtQuick
import Quickshell
import Quickshell.Io
import Caelestia
import Caelestia.Config
import Caelestia.I18n
import Caelestia.State
import qs.services

Scope {
    id: root

    Connections {
        function onGameModeChanged(): void {
            if (GlobalConfig.utilities.toasts.gameModeChanged)
                Toaster.toast(Tr.tr("Desktop effects"), RuntimeState.gameMode ? Tr.tr("Reduced shell effects") : Tr.tr("Restored shell effects"), "gamepad");
        }

        target: RuntimeState
    }

    IpcHandler {
        function isEnabled(): bool {
            return RuntimeState.gameMode;
        }

        function toggle(): void {
            RuntimeState.gameMode = !RuntimeState.gameMode;
        }

        function enable(): void {
            RuntimeState.gameMode = true;
        }

        function disable(): void {
            RuntimeState.gameMode = false;
        }

        target: "gameMode"
    }
}
