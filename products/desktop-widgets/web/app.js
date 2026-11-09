ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const $ = (id) => document.getElementById(id);
  ui.showApp(app);
  if (app.id !== "widget-rail") {
    ui.replace($("workspace"), [ui.node("p", "This identity has no Widget Rail presentation.", { class: "empty" })]);
    return;
  }
  const pending = new Set();
  const when = (value) => {
    if (!value) return "Not reported";
    const date = new Date(value);
    return Number.isFinite(date.getTime()) ? date.toLocaleString() : value;
  };
  function calendar(result) {
    if (!Array.isArray(result.events)) throw new Error("Invalid Calendar service response.");
    return result.events.length ? result.events.map((event) => {
      const card = ui.node("article", null, { class: "stack" });
      card.append(ui.node("strong", event.title || "(Untitled event)"),
        ui.node("p", `${when(event.start)}${event.end ? ` — ${when(event.end)}` : ""}`, { class: "small" }));
      if (event.location) card.append(ui.node("p", event.location, { class: "muted small" }));
      return card;
    }) : [ui.node("p", "No events today.", { class: "muted" })];
  }
  function tasks(result) {
    if (!Array.isArray(result.tasks)) throw new Error("Invalid Agent task service response.");
    return result.tasks.length ? result.tasks.map((task) => {
      const card = ui.node("article", null, { class: "stack" });
      card.append(ui.node("strong", task.purpose || task.id),
        ui.node("span", task.status || "Status not reported", { class: "pill" }),
        ui.node("p", `Created ${when(task.created_at)}`, { class: "small muted" }));
      return card;
    }) : [ui.node("p", "No Agent tasks.", { class: "muted" })];
  }
  function system(result) {
    const value = result.summary;
    if (!value || typeof value !== "object") throw new Error("Invalid OS telemetry response.");
    const usage = (item) => item ? `${item.used_mb.toLocaleString()} / ${item.total_mb.toLocaleString()} MiB` : "Not reported";
    const rate = (number) => typeof number === "number" ? `${number.toLocaleString()} B/s` : "Not reported";
    const values = ui.node("dl", null, { class: "detail-grid" });
    for (const [label, text] of [
      ["CPU", typeof value.cpu_percent === "number" ? `${value.cpu_percent.toFixed(1)}%` : "Not reported"],
      ["Memory", usage(value.memory)], ["Storage", usage(value.storage)],
      ["Download", rate(value.network_down_bps)], ["Upload", rate(value.network_up_bps)],
    ]) values.append(ui.node("dt", label), ui.node("dd", text));
    return [values, ui.node("p", value.fallback ? "The OS reports fallback telemetry." : "Reported by the OS telemetry service.", { class: "small muted" })];
  }
  const renderers = { calendar, tasks, system };
  async function load(source) {
    if (pending.has(source)) return;
    const state = $(`${source}-state`);
    const name = `widget-rail.${source}`;
    if (!ClawApp.tool(app, name)) {
      state.textContent = "Unavailable: this App does not declare this data source.";
      return;
    }
    pending.add(source);
    state.textContent = "Refreshing…";
    try {
      const result = await ClawApp.call(name, {});
      ui.replace($(source), renderers[source](result));
      state.textContent = "Updated";
    } catch (error) {
      ui.replace($(source), []);
      state.textContent = `Unavailable: ${error.message}`;
    } finally {
      pending.delete(source);
    }
  }
  const refresh = () => Promise.all(Object.keys(renderers).map(load));
  $("refresh").onclick = refresh;
  void refresh();
  const fast = setInterval(() => {
    if (!document.hidden) { void load("tasks"); void load("system"); }
  }, 5000);
  const slow = setInterval(() => { if (!document.hidden) void load("calendar"); }, 60000);
  window.addEventListener("pagehide", () => { clearInterval(fast); clearInterval(slow); }, { once: true });
}).catch((error) => {
  document.getElementById("notice").textContent = `Widget presentation unavailable: ${error.message}`;
});
