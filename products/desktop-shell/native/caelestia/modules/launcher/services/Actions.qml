pragma Singleton

import QtQuick
import Quickshell
import Caelestia.Config
import Caelestia.I18n
import qs.services
import qs.utils
import qs.modules.launcher

Searcher {
    id: root

    function transformSearch(search: string): string {
        return search.slice(GlobalConfig.launcher.actionPrefix.length);
    }

    list: variants.instances
    useFuzzy: GlobalConfig.launcher.useFuzzy.actions

    Variants {
        id: variants

        model: {
            const enableDangerous = GlobalConfig.launcher.enableDangerousActions;
            return GlobalConfig.launcher.actions.values.filter(a =>
                a.enabled && (enableDangerous || !a.dangerous) && root.supports(a.command ?? []));
        }

        Action {}
    }

    function powerAction(action: string): string {
        if (action === "suspendThenHibernate")
            return "suspend-then-hibernate";
        return Power.prompt(action) === "" ? "" : action;
    }

    function supports(command: list<string>): bool {
        if (command.length === 0 || ["loginctl", "systemctl"].includes(command[0]))
            return false;
        if (command[0] === "logout")
            return command.length === 1 && Config.session.enabled;
        if (powerAction(command[0]) !== "")
            return command.length === 1 && Config.session.enabled && Power.available;
        return true;
    }

    component Action: QtObject {
        required property var modelData
        readonly property string name: modelData.name ? Tr.trMarked(modelData.name) : Tr.trCtx("Unnamed", "launcher action with no name")
        readonly property string desc: modelData.description ? Tr.trMarked(modelData.description) : Tr.trCtx("No description", "launcher action with no description")
        readonly property string icon: modelData.icon ?? "help_outline"
        readonly property list<string> command: modelData.command ?? []
        readonly property bool enabled: modelData.enabled ?? true
        readonly property bool dangerous: modelData.dangerous ?? false

        function onClicked(list: AppList): void {
            if (!root.supports(command))
                return;

            const power = root.powerAction(command[0]);
            if (command[0] === "autocomplete" && command.length > 1) {
                list.search.text = `${GlobalConfig.launcher.actionPrefix}${command[1]} `;
            } else if (command[0] === "setMode" && command.length > 1) {
                list.screenState.launcher = false;
                Colours.setMode(command[1]);
            } else if (command[0] === "logout" || power !== "") {
                list.screenState.launcher = false;
                list.screenState.session = true;
                list.screenState.powerConfirmation = power;
            } else {
                list.screenState.launcher = false;
                Quickshell.execDetached(command);
            }
        }
    }
}
