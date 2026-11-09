ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const $ = (id) => document.getElementById(id);
  ui.showApp(app);
  if (app.id !== "widget-rail") {
    ui.replace($("workspace"), [ui.node("p", "This identity has no Widget Rail presentation.", { class: "empty" })]);
    return;
  }
  let shown = new Date();
  shown = new Date(shown.getFullYear(), shown.getMonth(), 1);
  let selected = new Date();
  let todayKey = "";
  const dateLabel = (date) => date.toLocaleDateString(undefined, { weekday: "long", year: "numeric", month: "long", day: "numeric" });
  const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

  function renderMonth() {
    const now = new Date();
    $("month").textContent = shown.toLocaleDateString(undefined, { month: "long", year: "numeric" });
    const first = new Date(shown.getFullYear(), shown.getMonth(), 1);
    const start = new Date(first); start.setDate(1 - first.getDay());
    const days = [];
    for (let index = 0; index < 42; index++) {
      const date = new Date(start); date.setDate(start.getDate() + index);
      const cell = ui.node("div", null, {
        class: `day${sameDay(date, now) ? " today" : ""}${date.getMonth() !== shown.getMonth() ? " outside" : ""}${sameDay(date, selected) ? " selected" : ""}`,
      });
      const button = ui.node("button", date.getDate(), { type: "button", class: "day-number", "aria-label": dateLabel(date), "aria-pressed": String(sameDay(date, selected)) });
      if (sameDay(date, now)) button.setAttribute("aria-current", "date");
      button.onclick = () => {
        selected = new Date(date);
        $("selected-date").textContent = dateLabel(selected);
        renderMonth();
      };
      cell.append(button); days.push(cell);
    }
    ui.replace($("calendar"), days);
    $("selected-date").textContent = dateLabel(selected);
  }
  function updateClock() {
    const now = new Date();
    $("clock").textContent = now.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
    $("today").textContent = dateLabel(now);
    $("zone").textContent = Intl.DateTimeFormat().resolvedOptions().timeZone || "Browser time zone not reported";
    const key = now.toDateString();
    if (key !== todayKey) { todayKey = key; renderMonth(); }
  }
  $("previous").onclick = () => { shown.setMonth(shown.getMonth() - 1); renderMonth(); };
  $("next").onclick = () => { shown.setMonth(shown.getMonth() + 1); renderMonth(); };
  $("go-today").onclick = () => {
    selected = new Date();
    shown = new Date(selected.getFullYear(), selected.getMonth(), 1);
    renderMonth();
  };
  updateClock();
  const timer = setInterval(updateClock, 30000);
  window.addEventListener("pagehide", () => clearInterval(timer), { once: true });
}).catch((error) => {
  document.getElementById("notice").textContent = `Widget presentation unavailable: ${error.message}`;
});
