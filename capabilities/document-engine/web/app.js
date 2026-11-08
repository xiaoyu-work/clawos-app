ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  const defaults = () => ({ path: document.querySelector("#path").value, file: document.querySelector("#path").value,
    text: document.querySelector("#text").value });
  const output = (value) => ui.output(document.querySelector("#result"), value);
  ui.actions(document.querySelector("#file-actions"), app, ["read", "info", "convert"], output, defaults);
  ui.actions(document.querySelector("#ai-actions"), app, ["summarize", "explain", "rewrite"], output, defaults);
  ui.allTools(document.querySelector("#more"), app, output, defaults);
});
