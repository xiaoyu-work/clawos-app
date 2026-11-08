ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  const output = (value) => ui.output(document.querySelector("#result"), value);
  const names = app.id === "hardware-center" ? ["cpu", "gpu", "pci", "usb", "memory", "storage", "drivers", "thermal"] :
    app.id === "crash-doctor" ? ["recent", "diagnose", "backtrace"] : ["interfaces", "routes", "dns", "tcp", "diagnose"];
  for (const name of names) {
    const card = ui.node("div", null, { class: "card" }); card.append(ui.node("h2", name.replaceAll("_", " ")));
    ui.actions(card, app, [{ command: name, label: "Inspect" }], output, () => ({ target: document.querySelector("#target").value }));
    document.querySelector("#sections").append(card);
  }
  const overview = app.id === "hardware-center" ? "summary" : app.id === "crash-doctor" ? "recent" : "interfaces";
  document.querySelector("#overview").onclick = (event) => void ui.run(event.target,
    () => ClawApp.call(overview), output, document.querySelector("#notice"));
  ui.allTools(document.querySelector("#more"), app, output, () => ({ target: document.querySelector("#target").value }));
});
