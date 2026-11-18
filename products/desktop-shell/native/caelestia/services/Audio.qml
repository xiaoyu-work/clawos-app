pragma Singleton
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import Caelestia
import Caelestia.Config
import Caelestia.I18n

Singleton {
    id: root

    property var state: ({})
    readonly property list<var> sinks: state.sinks ?? []
    readonly property list<var> sources: state.sources ?? []
    readonly property list<var> streams: state.streams ?? []
    readonly property var sink: sinks.find(node => node.id === state.defaults?.output?.id) ?? null
    readonly property var source: sources.find(node => node.id === state.defaults?.input?.id) ?? null
    readonly property bool muted: state.defaults?.output?.volume?.muted ?? false
    readonly property bool sourceMuted: state.defaults?.input?.volume?.muted ?? false
    readonly property real volume: state.defaults?.output?.volume?.linear ?? 0
    readonly property real sourceVolume: state.defaults?.input?.volume?.linear ?? 0
    readonly property string script: Quickshell.shellPath("utils/scripts/audio_control.py")
    readonly property bool canSetOutput: ShellState.controlOutput && sink !== null
    readonly property bool canSetInput: ShellState.controlInput && source !== null
    readonly property bool canRoute: ShellState.observeAudio && ShellState.routeAudio

    function setVolume(value: real): void {
        if (canSetOutput)
            apply("output-volume", "--value", Math.round(100 * Math.max(0, Math.min(1.5, GlobalConfig.services.maxVolume, value))));
    }

    function setSourceVolume(value: real): void {
        if (canSetInput)
            apply("input-volume", "--value", Math.round(100 * Math.max(0, Math.min(1, value))));
    }

    function incrementVolume(amount: real): void {
        setVolume(volume + (amount || GlobalConfig.services.audioIncrement));
    }

    function decrementVolume(amount: real): void {
        setVolume(volume - (amount || GlobalConfig.services.audioIncrement));
    }

    function incrementSourceVolume(amount: real): void {
        setSourceVolume(sourceVolume + (amount || GlobalConfig.services.audioIncrement));
    }

    function decrementSourceVolume(amount: real): void {
        setSourceVolume(sourceVolume - (amount || GlobalConfig.services.audioIncrement));
    }

    function setAudioSink(node: var): void {
        if (canRoute && node?.id)
            apply("output-default", "--target", node.id);
    }

    function setAudioSource(node: var): void {
        if (canRoute && node?.id)
            apply("input-default", "--target", node.id);
    }

    function setMuted(input: bool, value: bool): void {
        if (input ? canSetInput : canSetOutput)
            apply(input ? "input-mute" : "output-mute", "--value", value ? "on" : "off");
    }

    function getStreamName(stream: var): string {
        return stream.application_name || stream.description || stream.name || Tr.tr("Unknown audio stream");
    }

    function apply(action: string, field: string, value: var): void {
        if (effect.pending)
            return;
        effect.pending = true;
        effect.command = ["/usr/bin/python3", root.script, action, field, String(value)];
        effect.running = true;
    }

    Timer {
        running: ShellState.observeAudio
        repeat: true
        triggeredOnStart: true
        interval: 3000
        onTriggered: stateRead.running = true
    }

    Process {
        id: stateRead

        command: ["/usr/bin/python3", root.script, "status"]
        stdout: StdioCollector { id: listing }
        onExited: exitCode => {
            if (exitCode === 0)
                root.state = JSON.parse(listing.text);
        }
    }

    Process {
        id: effect

        property bool pending: false
        stdout: StdioCollector { id: result }
        onExited: exitCode => {
            pending = false;
            if (exitCode === 0 && JSON.parse(result.text).action_applied === true)
                stateRead.running = true;
            else
                Toaster.toast(Tr.tr("Audio change not confirmed"), Tr.tr("The OS audio service refused or did not confirm the action."), "error");
        }
        onRunningChanged: {
            if (pending && !running) {
                pending = false;
                Toaster.toast(Tr.tr("Audio control unavailable"), Tr.tr("The OS audio client could not be started."), "error");
            }
        }
    }
}
