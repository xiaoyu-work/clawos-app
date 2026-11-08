ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  const output = (value) => ui.output(document.querySelector("#status"), value);
  for (const item of [{ command: "previous", label: "Previous" }, { command: "play", label: "Play" },
    { command: "pause", label: "Pause" }, { command: "toggle", label: "Play / pause" },
    { command: "next", label: "Next" }, { command: "stop", label: "Stop" }, { command: "status", label: "Refresh status" }]) {
    const button = ui.node("button", item.label);
    button.onclick = () => void ui.run(button, () => ClawApp.call(item.command), output, document.querySelector("#notice"));
    document.querySelector("#controls").append(button);
  }
  ui.allTools(document.querySelector("#more"), app, output);
});
