ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  const sections = {
    "accessibility-manager": "Accessibility", "audio-manager": "Audio", "bluetooth-manager": "Bluetooth",
    "camera-manager": "Camera", "display-manager": "Displays", "desktop-manager": "Desktop sessions",
    "location-manager": "Location", "network-manager": "Network", "power-manager": "Power",
    "printer-manager": "Printers", "user-manager": "Users", "cosmic-settings": "App permissions and settings pages",
  };
  document.querySelector("#section").textContent = sections[app.id] || app.name;
  const inspect = app.id === "cosmic-settings" ? "permissions_list" : app.id === "desktop-manager" ? "list" : "status";
  const output = (value) => ui.output(document.querySelector("#result"), value);
  document.querySelector("#refresh").onclick = (event) => void ui.run(event.target, () => ClawApp.call(inspect),
    (value) => ui.output(document.querySelector("#state"), value), document.querySelector("#notice"));
  const visible = {
    "audio-manager": ["output-volume", "input-volume", "output-mute", "input-mute", "output-default", "profile"],
    "bluetooth-manager": ["scan", "pair", "pair-status", "pair-respond", "connect", "disconnect", "trust", "forget"],
    "network-manager": ["wifi-list", "connection-list", "wifi-connect", "wifi-disconnect", "wifi-toggle", "airplane", "vpn-list", "vpn-up", "vpn-down"],
    "display-manager": ["enable", "disable", "mode", "scale", "position", "mirror", "brightness", "apply-layout", "restore"],
    "power-manager": ["suspend", "hibernate", "reboot", "poweroff"],
    "printer-manager": ["capabilities", "jobs", "print", "cancel"],
    "user-manager": ["create-user", "delete-user", "set-password", "lock-user", "unlock-user", "create-group", "add-to-group", "restore"],
    "accessibility-manager": ["screen-reader", "magnifier", "invert", "filter"],
    "camera-manager": ["capture"], "desktop-manager": ["focus", "close", "restart"],
    "location-manager": ["locate", "timezone"],
    "cosmic-settings": ["permissions_show", "permissions_request", "permissions_revoke", "list_pages", "search", "open"],
  };
  ui.actions(document.querySelector("#actions"), app, visible[app.id] || [], output);
  ui.allTools(document.querySelector("#more"), app, output);
});
