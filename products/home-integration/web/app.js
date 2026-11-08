ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  const defaults = () => ({ service: document.querySelector("#service").value });
  ui.actions(document.querySelector("#status-actions"), app, ["status"], (value) => ui.output(document.querySelector("#status"), value));
  ui.actions(document.querySelector("#actions"), app, [{ command: "call", label: "Call service" },
    { command: "send", label: "Send notification" }], (value) => ui.output(document.querySelector("#result"), value), defaults);
  ui.allTools(document.querySelector("#more"), app, (value) => ui.output(document.querySelector("#result"), value), defaults);
});
