pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io
import Caelestia
import Caelestia.Config
import Caelestia.I18n
import Caelestia.Models
import qs.utils

Searcher {
    id: root

    function launch(entry: DesktopEntry): void {
        if (launcher.pending) {
            Toaster.toast(Tr.tr("Application launch pending"), Tr.tr("Wait for the current launch request to finish."), "hourglass_top");
            return;
        }
        launcher.appId = entry.id;
        launcher.pending = true;
        launcher.running = true;
    }

    function search(search: string): var {
        const prefix = GlobalConfig.launcher.specialPrefix;

        if (search.startsWith(`${prefix}i `)) {
            keys = ["id", "name"];
            weights = [0.9, 0.1];
        } else if (search.startsWith(`${prefix}c `)) {
            keys = ["categories", "name"];
            weights = [0.9, 0.1];
        } else if (search.startsWith(`${prefix}d `)) {
            keys = ["comment", "name"];
            weights = [0.9, 0.1];
        } else if (search.startsWith(`${prefix}e `)) {
            keys = ["execString", "name"];
            weights = [0.9, 0.1];
        } else if (search.startsWith(`${prefix}w `)) {
            keys = ["startupClass", "name"];
            weights = [0.9, 0.1];
        } else if (search.startsWith(`${prefix}g `)) {
            keys = ["genericName", "name"];
            weights = [0.9, 0.1];
        } else if (search.startsWith(`${prefix}k `)) {
            keys = ["keywords", "name"];
            weights = [0.9, 0.1];
        } else {
            keys = ["name"];
            weights = [1];

            if (!search.startsWith(`${prefix}t `))
                return query(search).map(e => e.entry);
        }

        const results = query(search.slice(prefix.length + 2)).map(e => e.entry);
        if (search.startsWith(`${prefix}t `))
            return results.filter(a => a.runInTerminal);
        return results;
    }

    function selector(item: var): string {
        return keys.map(k => item[k]).join(" ");
    }

    list: appDb.apps
    useFuzzy: GlobalConfig.launcher.useFuzzy.apps

    AppDb {
        id: appDb

        path: `${Paths.state}/apps.sqlite`
        favouriteApps: GlobalConfig.launcher.favouriteApps
        entries: DesktopEntries.applications.values.filter(a => !Strings.testRegexList(GlobalConfig.launcher.hiddenApps, a.id))
    }

    Process {
        id: launcher

        property string appId
        property bool pending: false

        command: ["/usr/bin/python3", Quickshell.shellPath("utils/scripts/desktop_launch.py"), appId]
        stdout: StdioCollector {
            id: launchOutput
        }

        onExited: exitCode => {
            pending = false;
            let response;
            try {
                response = JSON.parse(launchOutput.text);
            } catch (error) {
                Toaster.toast(Tr.tr("Could not launch application"), Tr.tr("The launch service returned an invalid response."), "error");
                return;
            }
            if (response === null || typeof response !== "object" || typeof response.ok !== "boolean") {
                Toaster.toast(Tr.tr("Could not launch application"), Tr.tr("The launch service returned an invalid response."), "error");
                return;
            }
            if (exitCode === 0 && response.ok === true)
                appDb.incrementFrequency(appId);
            else
                Toaster.toast(Tr.tr("Could not launch application"), String(response.error ?? Tr.tr("The launch request was not confirmed.")).slice(0, 1024), "error");
        }

        onRunningChanged: {
            if (pending && !running) {
                pending = false;
                Toaster.toast(Tr.tr("Could not launch application"), Tr.tr("The launch service could not be started."), "error");
            }
        }
    }
}
