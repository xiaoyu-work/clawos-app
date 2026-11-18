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
        launcher.submitted = false;
        launcher.failure = "";
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
        property bool submitted: false
        property string failure

        command: ["/usr/bin/python3", Quickshell.shellPath("utils/scripts/desktop_menu.py"), appId]
        stdout: SplitParser {
            onRead: line => {
                try {
                    const message = JSON.parse(line);
                    if (typeof message?.review_id === "string")
                        Toaster.toast(Tr.tr("Launch review %1").arg(message.review_id), Tr.tr("Approve once in Claw OS reviews."), "hourglass_top");
                    else if (message?.submitted === true)
                        launcher.submitted = true;
                    else if (typeof message?.error === "string")
                        launcher.failure = message.error.slice(0, 1024);
                } catch (_error) {
                    launcher.failure = Tr.tr("The launch service returned an invalid response.");
                }
            }
        }

        onExited: exitCode => {
            pending = false;
            if (exitCode === 0 && submitted)
                Toaster.toast(Tr.tr("Application launch requested"), Tr.tr("If the App needs its own permissions, review them in Claw OS."), "open_in_new");
            else
                Toaster.toast(Tr.tr("Could not launch application"), failure || Tr.tr("The OS did not confirm the launch request."), "error");
        }
    }
}
