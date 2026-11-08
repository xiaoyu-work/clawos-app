ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  const defaults = () => ({ mime: document.querySelector("#mime").value, primary: document.querySelector("#selection").value === "primary" });
  const result = (value) => ui.output(document.querySelector("#result"), value);
  for (const name of ["read", "status"]) {
    const button = document.querySelector(`#${name}`);
    button.disabled = !ClawApp.tool(app, name);
    button.onclick = () => void ui.run(button, () => ClawApp.call(name, name === "read" ? defaults() : { primary: defaults().primary }),
      (value) => { document.querySelector("#content").textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2); },
      document.querySelector("#notice"));
  }
  ui.actions(document.querySelector("#actions"), app, ["types", "write", "clear"], result, defaults);
  ui.allTools(document.querySelector("#more"), app, result, defaults);
  if (!app.tools.length) document.querySelector("#notice").textContent =
    "The native history panel requires its desktop integration. This identity does not expose selection or history tools.";
});
