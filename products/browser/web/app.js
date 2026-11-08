ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  ui.showApp(app);
  const address = document.querySelector("#address");
  const notice = document.querySelector("#notice");
  const output = (value) => ui.output(document.querySelector("#details"), value);
  function results(value) {
    const items = ui.rows(value);
    if (!items.length) { ui.output(document.querySelector("#results"), value); return; }
    ui.replace(document.querySelector("#results"), items.map((item) => {
      const card = ui.node("article", null, { class: "card" });
      card.append(ui.node("h3", item.title || item.url || item.id), ui.node("p", item.snippet || item.description || item.url || ""));
      if (item.url) {
        const button = ui.node("button", "Use URL"); button.onclick = () => { address.value = item.url; };
        card.append(button);
      }
      return card;
    }));
  }
  document.querySelector("#go").textContent = app.id === "search" ? "Search" : app.id === "web" ? "Read page" : "Navigate tab";
  document.querySelector("#navigation").onsubmit = (event) => {
    event.preventDefault();
    if (app.id === "search") ui.command(app, "web", { query: address.value }, results);
    else if (app.id === "web") void ui.run(document.querySelector("#go"),
      () => ClawApp.call("read", { url: address.value }), results, notice);
    else ui.command(app, "go", { url: address.value }, results);
  };
  ui.actions(document.querySelector("#actions"), app, ["image", "scrape", "screenshot", "submit", "summarize",
    "list", "activate", "query", "click", "fill", "fill_secret", "snapshot", "eval"], output,
  () => ({ url: address.value, page_url: address.value }));
  ui.allTools(document.querySelector("#more"), app, output, () => ({ url: address.value, page_url: address.value }));
  if (app.id === "browser-attached") void ui.run(null, () => ClawApp.call("list"), results, notice);
});
