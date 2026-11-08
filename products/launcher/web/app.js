ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  function render(value) {
    const items = ui.rows(value, ["apps", "applications", "results", "items"]);
    if (!items.length) { ui.output(document.querySelector("#apps"), value); return; }
    ui.replace(document.querySelector("#apps"), items.map((item) => {
      const card = ui.node("article", null, { class: "card" });
      card.append(ui.node("h2", item.name || item.id), ui.node("p", item.description || item.id || ""));
      ui.actions(card, app, [{ command: "open", label: "Launch through OS" }],
        (result) => ui.output(document.querySelector("#result"), result), () => ({ app_id: item.id || item.app_id }));
      return card;
    }));
  }
  document.querySelector("#search").onsubmit = (event) => {
    event.preventDefault();
    void ui.run(event.target.querySelector("button"), () => ClawApp.call("find", { query: document.querySelector("#query").value }),
      render, document.querySelector("#notice"));
  };
  document.querySelector("#all").onclick = (event) => void ui.run(event.target, () => ClawApp.call("list"), render, document.querySelector("#notice"));
  ui.actions(document.querySelector("#actions"), app, ["recent", "is-running"], render);
  ui.allTools(document.querySelector("#more"), app, (value) => ui.output(document.querySelector("#result"), value));
});
