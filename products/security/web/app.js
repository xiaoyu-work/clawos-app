ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  document.querySelector("#refresh").onclick = (event) => void ui.run(event.target,
    () => ClawApp.call(app.id === "security-center" ? "summary" : "status"),
    (value) => ui.output(document.querySelector("#state"), value), document.querySelector("#notice"));
  const names = app.id === "security-center" ? ["auth", "ssh", "sudo", "mac", "ports", "events"] :
    app.id === "firewall-manager" ? ["add", "delete", "clear", "restore"] :
    ["authorize", "block", "unblock", "eject", "restore"];
  ui.actions(document.querySelector("#actions"), app, names, (value) => ui.output(document.querySelector("#result"), value));
  ui.allTools(document.querySelector("#more"), app, (value) => ui.output(document.querySelector("#result"), value));
});
