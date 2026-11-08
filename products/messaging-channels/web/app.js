ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  ui.actions(document.querySelector("#lifecycle"), app, ["status", "configure", "start", "stop"],
    (value) => ui.output(document.querySelector("#state"), value));
  const defaults = () => ({ text: document.querySelector("#text").value });
  ui.actions(document.querySelector("#actions"), app, [{ command: "send", label: "Send message" },
    { command: "reply", label: "Review channel reply" }], (value) => ui.output(document.querySelector("#result"), value), defaults);
  ui.allTools(document.querySelector("#more"), app, (value) => ui.output(document.querySelector("#result"), value), defaults);
});
