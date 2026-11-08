ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app); const form = document.querySelector("#request");
  const output = (value) => ui.output(document.querySelector("#response"), value);
  form.onsubmit = (event) => {
    event.preventDefault();
    const args = { method: form.elements.method.value, url: form.elements.url.value };
    if (form.elements.data.value) args.data = form.elements.data.value;
    void ui.run(form.querySelector("button"), () => ClawApp.call("fetch", args), output, document.querySelector("#notice"));
  };
  ui.actions(document.querySelector("#actions"), app, [{ command: "download", label: "Download to authorized path" }], output,
    () => ({ url: form.elements.url.value }));
  ui.allTools(document.querySelector("#more"), app, output, () => ({ url: form.elements.url.value }));
});
