ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  function render(value) {
    const items = ui.rows(value, ["events", "entries", "items", "records"]);
    if (!items.length) { ui.output(document.querySelector("#events"), value); return; }
    ui.table(document.querySelector("#events"), items, [
      { label: "Time", value: (item) => item.timestamp || item.time }, { label: "Source", value: (item) => item.source || item.app },
      { label: "Event", value: (item) => item.message || item.kind || item.event }, { label: "Status", key: "status" },
    ], { label: "Inspect", run: (item) => ui.output(document.querySelector("#details"), item) });
  }
  document.querySelector("#refresh").onclick = (event) => void ui.run(event.target,
    () => ClawApp.call(app.id === "event-center" ? "recent" : "read"), render, document.querySelector("#notice"));
  document.querySelector("#search").disabled = !ClawApp.tool(app, "search");
  document.querySelector("#search").onclick = () => ui.command(app, "search", { query: document.querySelector("#query").value }, render);
  ui.actions(document.querySelector("#actions"), app, ["status", "watch-pid", "tail", "write"], render);
  ui.allTools(document.querySelector("#more"), app, (value) => ui.output(document.querySelector("#details"), value));
});
