ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  const target = document.querySelector("#target");
  const defaults = () => app.id === "systemd" ? { unit: target.value } : { target: target.value };
  document.querySelector("#inspect").onclick = (event) => void ui.run(event.target,
    () => ClawApp.call(app.id === "systemd" ? "status" : "inspect", defaults()),
    (value) => ui.output(document.querySelector("#state"), value), document.querySelector("#notice"));
  const actions = app.id === "systemd" ? ["start", "stop", "restart", "reload", "enable", "disable"] : ["validate", "apply", "restore"];
  ui.actions(document.querySelector("#actions"), app, actions, (value) => ui.output(document.querySelector("#result"), value), defaults);
  ui.allTools(document.querySelector("#more"), app, (value) => ui.output(document.querySelector("#result"), value), defaults);
});
