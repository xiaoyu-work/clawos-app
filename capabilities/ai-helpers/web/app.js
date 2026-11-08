ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  const output = (value) => ui.output(document.querySelector("#result"), value);
  document.querySelector("#summarize").onsubmit = (event) => {
    event.preventDefault();
    void ui.run(event.target.querySelector("button"), () => ClawApp.call("run", { text: event.target.elements.text.value }),
      output, document.querySelector("#notice"));
  };
  ui.allTools(document.querySelector("#more"), app, output);
});
