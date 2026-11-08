ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app); let selected = null;
  function defaults() {
    const value = { runtime: document.querySelector("#runtime").value, target: selected && (selected.id || selected.name) };
    if (document.querySelector("#namespace").value) value.namespace = document.querySelector("#namespace").value;
    return value;
  }
  function render(value) {
    ui.table(document.querySelector("#containers"), ui.rows(value, ["containers", "items"]), [
      { label: "Name", value: (item) => item.name || item.names || item.id },
      { label: "Image", key: "image" }, { label: "State", value: (item) => item.state || item.status },
    ], { label: "Inspect", run: (item) => {
      selected = item; document.querySelector("#selected").textContent = item.name || item.id;
      document.querySelector("#actions").replaceChildren();
      ui.actions(document.querySelector("#actions"), app, ["inspect", "logs", "processes", "stats", "start", "stop",
        "restart", "pause", "unpause", "kill", "remove"], (result) => ui.output(document.querySelector("#result"), result), defaults);
    } });
  }
  document.querySelector("#refresh").onclick = (event) => void ui.run(event.target,
    () => ClawApp.call("list", defaults()), render, document.querySelector("#notice"));
  ui.allTools(document.querySelector("#more"), app, (value) => ui.output(document.querySelector("#result"), value), defaults);
});
