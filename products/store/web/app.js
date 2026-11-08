ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  const defaults = () => ({ name: document.querySelector("#package").value, package: document.querySelector("#package").value });
  function render(value) {
    const items = ui.rows(value, ["packages", "results", "items"]);
    if (!items.length) { ui.output(document.querySelector("#packages"), value); return; }
    ui.table(document.querySelector("#packages"), items, [
      { label: "Package", value: (item) => item.name || item.package },
      { label: "Version", key: "version" }, { label: "Description", key: "description" },
    ], { label: "Select", run: (item) => { document.querySelector("#package").value = item.name || item.package;
      ui.output(document.querySelector("#result"), item); } });
  }
  document.querySelector("#search").onsubmit = (event) => { event.preventDefault(); void ui.run(event.target.querySelector("button"),
    () => ClawApp.call("search", { query: document.querySelector("#query").value }), render, document.querySelector("#notice")); };
  document.querySelector("#installed").onclick = (event) => void ui.run(event.target,
    () => ClawApp.call(app.id === "pkg" ? "list" : "installed"), render, document.querySelector("#notice"));
  ui.actions(document.querySelector("#actions"), app, ["show", "has", "need", "remove", "purge", "upgrade", "install-version", "hold", "unhold", "open"],
    (value) => ui.output(document.querySelector("#result"), value), defaults);
  ui.allTools(document.querySelector("#more"), app, (value) => ui.output(document.querySelector("#result"), value), defaults);
});
