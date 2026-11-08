ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  const notice = document.querySelector("#notice");
  const output = (value) => ui.output(document.querySelector("#result"), value);
  document.querySelector("#kv").hidden = app.id !== "kv";
  document.querySelector("#db").hidden = app.id !== "db";
  if (app.id === "kv") {
    const key = document.querySelector("#key");
    for (const item of [{ button: "get", command: "get" }, { button: "delete", command: "del" },
      { button: "set", command: "set" }, { button: "list", command: "list" }]) {
      const button = document.querySelector(`#${item.button}`);
      button.onclick = () => void ui.run(button, () => {
        const args = item.command === "list" ? { pattern: document.querySelector("#pattern").value } : { key: key.value };
        if (item.command === "set") args.value = document.querySelector("#value").value;
        return ClawApp.call(item.command, args);
      }, (value) => {
        output(value);
        if (item.command === "get" && typeof value === "string") document.querySelector("#value").value = value;
      }, notice);
    }
  } else {
    const defaults = () => ({ database: document.querySelector("#database").value });
    for (const item of [{ button: "query", command: "query" }, { button: "execute", command: "exec" }]) {
      const button = document.querySelector(`#${item.button}`);
      button.onclick = () => void ui.run(button, () => ClawApp.call(item.command, {
        ...defaults(), sql: document.querySelector("#sql").value,
      }), output, notice);
    }
    ui.actions(document.querySelector("#db-actions"), app, ["databases", "tables", "schema"], output, defaults);
  }
  ui.allTools(document.querySelector("#more"), app, output);
});
