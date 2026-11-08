ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  const defaults = () => ({ text: document.querySelector("#text").value });
  const output = (value) => ui.output(document.querySelector("#result"), value);
  ui.actions(document.querySelector("#actions"), app, [{ command: "send", label: "Review delivery parameters" }, "status"], output, defaults);
  ui.allTools(document.querySelector("#more"), app, output, defaults);
});
