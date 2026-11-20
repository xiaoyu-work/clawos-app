pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import qs.services

Variants {
    model: Screens.screens

    Scope {
        id: scope

        required property ShellScreen modelData

        TopBar {
            id: top

            screen: scope.modelData
            onMenuRequested: name => menu.toggle(name)
            onPinMenuRequested: (id, x) => {
                menu.pinId = id;
                menu.pinX = x;
                menu.page = "pin";
            }
            onLaunched: menu.page = ""
        }

        QuietMenu {
            id: menu

            screen: scope.modelData
            bar: top
        }

        ContentWindow {
            id: content

            screen: scope.modelData
            topInset: top.implicitHeight
            topBar: top
        }
    }
}
