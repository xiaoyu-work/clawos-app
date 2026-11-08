ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  const defaults = () => ({ repo: document.querySelector("#repo").value,
    credential: document.querySelector("#credential").value, snapshot: document.querySelector("#snapshot").value,
    id: document.querySelector("#snapshot").value });
  const result = (value) => ui.output(document.querySelector("#result"), value);
  document.querySelector("#refresh").onclick = (event) => void ui.run(event.target, () => ClawApp.call(
    app.id === "backup-center" ? "snapshots" : "list",
    app.id === "backup-center" ? { repo: defaults().repo, credential: defaults().credential } : {},
  ), (value) => {
    const items = ui.rows(value, ["snapshots", "items"]);
    if (!items.length) { ui.output(document.querySelector("#snapshots"), value); return; }
    ui.table(document.querySelector("#snapshots"), items, [
      { label: "Snapshot", value: (item) => item.id || item.short_id },
      { label: "Time", value: (item) => item.time || item.created_at }, { label: "Description", value: (item) => item.description || item.tags },
    ], { label: "Select", run: (item) => { document.querySelector("#snapshot").value = item.id || item.short_id; result(item); } });
  }, document.querySelector("#notice"));
  ui.actions(document.querySelector("#actions"), app, ["init", "check", "backup", "restore", "forget", "retention", "status", "create", "delete", "rollback"],
    result, defaults);
  ui.allTools(document.querySelector("#more"), app, result, defaults);
  if (app.id === "system-snapshot") { document.querySelector("#repo").hidden = true; document.querySelector("#credential").hidden = true; }
});
