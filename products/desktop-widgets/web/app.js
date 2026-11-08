ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  function update() {
    const now = new Date();
    document.querySelector("#clock").textContent = now.toLocaleTimeString();
    document.querySelector("#zone").textContent = Intl.DateTimeFormat().resolvedOptions().timeZone;
    document.querySelector("#date").textContent = now.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    document.querySelector("#weekday").textContent = now.toLocaleDateString(undefined, { weekday: "long" });
  }
  update(); setInterval(update, 1000);
  const now = new Date(); const first = new Date(now.getFullYear(), now.getMonth(), 1);
  const start = new Date(first); start.setDate(1 - first.getDay());
  for (let index = 0; index < 42; index++) {
    const date = new Date(start); date.setDate(start.getDate() + index);
    document.querySelector("#calendar").append(ui.node("div", date.getDate(), {
      class: `day${date.toDateString() === now.toDateString() ? " today" : ""}`,
    }));
  }
  ui.allTools(document.querySelector("#more"), app, () => {});
});
