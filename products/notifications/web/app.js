ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app); const form = document.querySelector("#send");
  const output = (value) => ui.output(document.querySelector("#notifications"), value);
  form.onsubmit = (event) => {
    event.preventDefault();
    const text = form.elements.message.value;
    void ui.run(form.querySelector("button"), () => ClawApp.call(app.id === "notify" ? "send" : "post",
      app.id === "notify" ? { message: text, urgent: form.elements.urgent.checked } : { summary: text, body: "" }),
    output, document.querySelector("#notice"));
  };
  document.querySelector("#refresh").disabled = !ClawApp.tool(app, "list");
  document.querySelector("#refresh").onclick = (event) => void ui.run(event.target, () => ClawApp.call("list"), output, document.querySelector("#notice"));
  ui.actions(document.querySelector("#actions"), app, ["close"], output);
  ui.allTools(document.querySelector("#more"), app, output);
});
