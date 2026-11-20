import Quickshell

PersistentProperties {
    required property ShellScreen modelData

    // Drawer visibilities
    property bool osd
    property bool session
    property bool dashboard
    property bool utilities
    property bool sidebar

    // Dashboard state
    property int dashboardTab
    property date dashboardDate: new Date()
}
