pragma Singleton
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import Caelestia.Config
import Caelestia.I18n
import qs.components.misc

Singleton {
    id: root

    readonly property string script: Quickshell.shellPath("utils/scripts/brightness_control.py")
    property var state: ({})
    readonly property var backlight: state.outputs?.length === 1 && state.backlights?.length === 1
        && state.backlights[0].maximum > 0 ? state.backlights[0] : null

    function getMonitorForScreen(screen: ShellScreen): var {
        return variants.instances.find(monitor => monitor.modelData === screen);
    }

    function adjust(step: real): void {
        const monitor = variants.instances.find(m => Hypr.monitorFor(m.modelData)?.focused);
        if (monitor?.adjustable)
            monitor.setBrightness(monitor.brightness + step);
    }

    Variants {
        id: variants
        model: Quickshell.screens
        Monitor {}
    }

    Timer {
        running: ShellState.observeBrightness
        repeat: true
        triggeredOnStart: true
        interval: 5000
        onTriggered: stateRead.running = true
    }

    Process {
        id: stateRead
        command: ["/usr/bin/python3", root.script, "status"]
        stdout: StdioCollector { id: listing }
        onExited: exitCode => {
            root.state = exitCode === 0 ? JSON.parse(listing.text) : ({});
        }
    }

    Process {
        id: effect
        stdout: StdioCollector { id: result }
        onExited: exitCode => {
            if (exitCode !== 0 || !JSON.parse(result.text).after)
                Toaster.toast(Tr.tr("Brightness change not confirmed"),
                    Tr.tr("The OS display service refused or did not confirm the action."), "error");
            stateRead.running = true;
        }
    }

    CustomShortcut {
        name: "brightnessUp"
        description: "Increase brightness"
        onPressed: root.adjust(GlobalConfig.services.brightnessIncrement)
    }

    CustomShortcut {
        name: "brightnessDown"
        description: "Decrease brightness"
        onPressed: root.adjust(-GlobalConfig.services.brightnessIncrement)
    }

    component Monitor: QtObject {
        required property ShellScreen modelData
        readonly property bool available: root.backlight !== null
            && root.state.outputs[0].name === modelData.name
        readonly property bool adjustable: available && ShellState.controlBrightness
        readonly property real brightness: available ? root.backlight.percent / 100 : 0

        function setBrightness(value: real): void {
            if (!adjustable || !Number.isFinite(value) || effect.running)
                return;
            const percent = Math.max(1, Math.min(100, Math.round(value * 100)));
            if (percent === root.backlight.percent)
                return;
            effect.command = ["/usr/bin/python3", root.script, "brightness", root.backlight.name, String(percent)];
            effect.running = true;
        }
    }
}
