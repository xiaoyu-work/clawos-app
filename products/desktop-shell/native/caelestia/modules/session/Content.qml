pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Caelestia
import Caelestia.Config
import Caelestia.I18n
import qs.components
import qs.components.controls
import qs.services
import qs.utils

Column {
    id: root

    required property ScreenState screenState

    readonly property string powerPrompt: Power.prompt(screenState.powerConfirmation)

    function dismissPowerPrompt(): void {
        screenState.powerConfirmation = "";
        logout.forceActiveFocus();
    }

    padding: Tokens.padding.large
    rightPadding: CUtils.clamp(padding - Config.border.thickness, 0, padding)
    spacing: Tokens.spacing.large

    SessionButton {
        id: logout

        icon: Config.session.icons.logout
        closesSession: true

        KeyNavigation.down: shutdown.enabled ? shutdown : null

        Component.onCompleted: forceActiveFocus()

        Connections {
            function onLauncherChanged(): void {
                if (!root.screenState.launcher)
                    logout.forceActiveFocus();
            }

            target: root.screenState
        }
    }

    SessionButton {
        id: shutdown

        icon: Config.session.icons.shutdown
        powerAction: "poweroff"

        KeyNavigation.up: logout
        KeyNavigation.down: hibernate
    }

    Loader {
        active: Config.paths.sessionGif.trim() !== ""

        sourceComponent: AnimatedImage {
            width: Tokens.sizes.session.button
            height: Tokens.sizes.session.button
            sourceSize.width: width * ((QsWindow.window as QsWindow)?.devicePixelRatio ?? 1)

            playing: visible
            asynchronous: true
            speed: Config.general.sessionGifSpeed
            source: Paths.absolutePath(Config.paths.sessionGif)
            fillMode: AnimatedImage.PreserveAspectFit
        }
    }

    SessionButton {
        id: hibernate

        icon: Config.session.icons.hibernate
        powerAction: "hibernate"

        KeyNavigation.up: shutdown
        KeyNavigation.down: reboot
    }

    SessionButton {
        id: reboot

        icon: Config.session.icons.reboot
        powerAction: "reboot"

        KeyNavigation.up: hibernate
    }

    Column {
        visible: root.screenState.session && root.powerPrompt !== ""
        spacing: Tokens.spacing.small
        onVisibleChanged: {
            if (visible)
                cancelPower.forceActiveFocus();
        }

        StyledText { text: root.powerPrompt }

        Row {
            spacing: Tokens.spacing.small

            TextButton {
                id: cancelPower

                text: Tr.tr("Cancel")
                onClicked: root.dismissPowerPrompt()
                Keys.onPressed: event => {
                    if ([Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape].includes(event.key)) {
                        root.dismissPowerPrompt();
                        event.accepted = true;
                    }
                }
                KeyNavigation.right: confirmPower
                KeyNavigation.tab: confirmPower
            }

            TextButton {
                id: confirmPower

                text: Tr.tr("Confirm")
                enabled: Power.available && !Power.busy
                onClicked: {
                    Power.request(root.screenState.powerConfirmation);
                    root.dismissPowerPrompt();
                }
                Keys.onReturnPressed: clicked()
                Keys.onEnterPressed: clicked()
                Keys.onEscapePressed: root.dismissPowerPrompt()
                KeyNavigation.left: cancelPower
                KeyNavigation.backtab: cancelPower
            }
        }
    }

    component SessionButton: IconButton {
        id: button

        property string powerAction
        property bool closesSession: false
        enabled: closesSession || (Power.available && !Power.busy)
        disabled: !enabled

        function exec(): void {
            if (closesSession) {
                Qt.quit();
            } else if (enabled) {
                root.screenState.powerConfirmation = powerAction;
            }
        }

        implicitWidth: Tokens.sizes.session.button
        implicitHeight: Tokens.sizes.session.button

        inactiveColour: activeFocus ? Colours.palette.m3secondaryContainer : Colours.tPalette.m3surfaceContainer
        inactiveOnColour: activeFocus ? Colours.palette.m3onSecondaryContainer : Colours.palette.m3onSurface
        radius: pressed ? Tokens.rounding.medium : activeFocus ? Tokens.rounding.extraLarge : Tokens.rounding.largeIncreased
        font: Tokens.font.icon.builders.large.scale(1.3).build()
        onClicked: exec()

        Keys.onEnterPressed: exec()
        Keys.onReturnPressed: exec()
        Keys.onEscapePressed: root.screenState.session = false
        Keys.onPressed: event => {
            if (!Config.session.vimKeybinds)
                return;

            if (event.modifiers & Qt.ControlModifier) {
                if ((event.key === Qt.Key_J || event.key === Qt.Key_N) && KeyNavigation.down) {
                    KeyNavigation.down.focus = true;
                    event.accepted = true;
                } else if ((event.key === Qt.Key_K || event.key === Qt.Key_P) && KeyNavigation.up) {
                    KeyNavigation.up.focus = true;
                    event.accepted = true;
                }
            } else if (event.key === Qt.Key_Tab && KeyNavigation.down) {
                KeyNavigation.down.focus = true;
                event.accepted = true;
            } else if (event.key === Qt.Key_Backtab || (event.key === Qt.Key_Tab && (event.modifiers & Qt.ShiftModifier))) {
                if (KeyNavigation.up) {
                    KeyNavigation.up.focus = true;
                    event.accepted = true;
                }
            }
        }
    }
}
