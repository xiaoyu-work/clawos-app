ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  ui.showApp(app);
  let month = new Date();
  let events = [];
  const notice = document.querySelector("#notice");
  const provider = document.querySelector("#provider");
  const defaults = () => ({ provider: provider.value, start: month.toISOString(),
    end: new Date(month.getFullYear(), month.getMonth(), month.getDate(), month.getHours() + 1).toISOString() });
  function render() {
    document.querySelector("#month").textContent = month.toLocaleDateString(undefined, { year: "numeric", month: "long" });
    const first = new Date(month.getFullYear(), month.getMonth(), 1);
    const start = new Date(first); start.setDate(1 - first.getDay());
    const cells = [];
    for (let index = 0; index < 42; index++) {
      const date = new Date(start); date.setDate(start.getDate() + index);
      const cell = ui.node("div", null, { class: "day" });
      if (date.toDateString() === new Date().toDateString()) cell.classList.add("today");
      cell.append(ui.node("span", date.getDate()));
      for (const event of events.filter((item) => new Date(item.start).toDateString() === date.toDateString())) {
        const button = ui.node("button", event.title || event.summary || event.id);
        button.onclick = () => {
          ui.output(document.querySelector("#details"), event);
          const actions = ui.node("div", null, { class: "toolbar" });
          ui.actions(actions, app, [{ command: "update", label: "Edit event" }, { command: "delete", label: "Delete event" }],
            () => load(), () => ({ provider: provider.value, id: event.id, ...event }));
          document.querySelector("#details").append(actions);
        };
        cell.append(button);
      }
      cells.push(cell);
    }
    ui.replace(document.querySelector("#calendar"), cells);
  }
  function load() {
    render();
    if (!ClawApp.tool(app, "list")) {
      notice.textContent = "This native entry has no event service. The Calendar App entry provides event operations.";
      return;
    }
    return ui.run(document.querySelector("#refresh"), () => ClawApp.call("list", {
      provider: provider.value,
      from: new Date(month.getFullYear(), month.getMonth(), 1).toISOString(),
      to: new Date(month.getFullYear(), month.getMonth() + 1, 1).toISOString(),
    }), (result) => { events = ui.rows(result); render(); }, notice);
  }
  document.querySelector("#previous").onclick = () => { month.setMonth(month.getMonth() - 1); void load(); };
  document.querySelector("#next").onclick = () => { month.setMonth(month.getMonth() + 1); void load(); };
  document.querySelector("#refresh").onclick = load;
  provider.onchange = load;
  document.querySelector("#create").disabled = !ClawApp.tool(app, "create");
  document.querySelector("#create").onclick = () => ui.command(app, "create", defaults(), () => load());
  ui.allTools(document.querySelector("#more"), app, (value) => ui.output(document.querySelector("#details"), value), defaults);
  void load();
});
