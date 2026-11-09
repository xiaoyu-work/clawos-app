ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const root = document.getElementById("workspace");
  const notice = document.getElementById("notice");
  const entries = document.getElementById("events");
  const count = document.getElementById("count");
  let busy = false;
  let reviewing = false;
  ui.showApp(app);

  function detail(value) {
    if (value === null || value === undefined) return ui.node("p", "Not reported", { class: "muted" });
    if (typeof value !== "object") return ui.node("p", String(value), { class: "prose" });
    const box = ui.node("div", null, { class: "stack" });
    if (Array.isArray(value)) {
      if (!value.length) box.append(ui.node("p", "No records returned.", { class: "muted" }));
      for (const item of value) box.append(detail(item));
    } else {
      const grid = ui.node("dl", null, { class: "detail-grid" });
      for (const [key, item] of Object.entries(value)) {
        grid.append(ui.node("dt", key.replaceAll("_", " ")));
        const cell = ui.node("dd"); cell.append(detail(item)); grid.append(cell);
      }
      box.append(grid.children.length ? grid : ui.node("p", "No additional fields returned.", { class: "muted" }));
    }
    return box;
  }
  function evidence(title, value) {
    document.getElementById("detail-title").textContent = title;
    ui.replace(document.getElementById("details"), [detail(value)]);
  }
  function section(title, text) {
    const card = ui.node("section", null, { class: "card stack" });
    card.append(ui.node("h2", title), ui.node("p", text)); root.append(card); return card;
  }
  function field(parent, label, attributes = {}, tag = "input") {
    const row = ui.node("label", label); const input = ui.node(tag, null, attributes);
    row.append(input); parent.append(row); return input;
  }
  function choose(parent, label, choices) {
    const select = field(parent, label, {}, "select");
    for (const [value, text] of choices) select.append(ui.node("option", text, { value }));
    return select;
  }
  function button(parent, label, action, className = "") {
    const control = ui.node("button", label, { type: "button", class: className });
    control.onclick = () => { try { action(control); } catch (error) { notice.textContent = error.message; } };
    parent.append(control); return control;
  }
  function bounded(input, name, maximum = 1000) {
    const value = Number(input.value);
    if (input.value === "" || !Number.isInteger(value) || value < 1 || value > maximum) throw new Error(`${name} must be an integer from 1 to ${maximum}.`);
    return value;
  }
  async function request(control, command, args, done, status = notice) {
    if (busy) return;
    busy = true;
    try {
      await ui.run(control, () => {
        const tool = ClawApp.tool(app, command);
        if (!tool) throw new Error(`This entry does not declare ${command}.`);
        return ClawApp.call(tool.name, args);
      }, done, status);
    } finally { busy = false; }
  }
  function render(value, order) {
    const items = value && (Array.isArray(value.entries) ? value.entries : Array.isArray(value.events) ? value.events : Array.isArray(value.records) ? value.records : null);
    if (!items) {
      count.textContent = "No structured record list supplied.";
      ui.replace(entries, [detail(value)]); return;
    }
    if (items.some((item) => !item || typeof item !== "object" || Array.isArray(item))) throw new Error("The service returned an unrecognized event record. No watch or write was made.");
    count.textContent = `${items.length} returned${Number.isInteger(value.total) ? ` / ${value.total} matching` : ""}. ${order}`;
    if (!items.length) { ui.replace(entries, [ui.node("p", "No records matched this query. This is not a claim that the system audit trail is empty.", { class: "empty" })]); return; }
    ui.table(entries, items, [
      { label: "Time", value: (item) => item.timestamp || item.time || "Not reported" },
      { label: "Source / App", value: (item) => item.source || item.app || "Not reported" },
      { label: "Event", value: (item) => typeof item.message === "string" ? item.message : item.kind || item.event || "Open details" },
      { label: "Level / status", value: (item) => item.level || item.status || "Not reported" },
    ], { label: "Details", run: (item) => evidence("Selected event record", item) });
  }
  function review(command, args, title, explanation) {
    if (busy || reviewing) return;
    reviewing = true;
    const dialog = ui.node("dialog"); const form = ui.node("form");
    const check = ui.node("input", null, { type: "checkbox", required: "" });
    const label = ui.node("label", "I confirm this explicit request."); label.append(check);
    const status = ui.node("p", "", { class: "notice", role: "status", "aria-live": "polite" });
    const cancel = ui.node("button", "Cancel", { type: "button" });
    const execute = ui.node("button", title, { type: "submit", class: "primary" });
    const actions = ui.node("div", null, { class: "toolbar" }); actions.append(cancel, execute);
    form.append(ui.node("p", explanation), detail(args), label, status, actions);
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (!check.checked || busy) return;
      cancel.disabled = true;
      await request(execute, command, args, (value) => {
        evidence(title, value);
        notice.textContent = "Response received. Inspect service or record state before retrying; no automatic retry.";
        dialog.close();
      }, status);
      cancel.disabled = false; check.checked = false;
      if (dialog.open) status.append(ui.node("span", " The request may have completed. Verify state before retrying."));
    };
    cancel.onclick = () => dialog.close();
    dialog.addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
    dialog.addEventListener("close", () => { reviewing = false; dialog.remove(); });
    dialog.append(ui.node("h2", title), form); document.body.append(dialog); dialog.showModal();
  }

  if (app.id === "event-center") {
    const filters = section("System event history", "This is the existing OS event service, not Agent tasks, an audit store or a new event subscription engine.");
    const source = choose(filters, "Source", [["", "All declared sources"], ["udev", "Devices (udev)"], ["systemd", "Services"], ["journal", "Journal"], ["storage", "Storage"], ["security", "Security"], ["process", "Process"]]);
    const limit = field(filters, "Maximum events", { type: "number", min: "1", max: "1000", step: "1", value: "100" });
    button(filters, "Load recent events", (control) => {
      const args = { limit: bounded(limit, "Event limit") };
      if (source.value) args.source = source.value;
      void request(control, "recent", args, (value) => render(value, "Order is supplied by the event service."));
    }, "primary");
    button(filters, "Inspect source health", (control) => void request(control, "status", {}, (value) => evidence("Event service and source health", value)));
    const watch = ui.node("details", null, { class: "card stack" });
    watch.append(ui.node("summary", "Explicit process-exit watch"), ui.node("p", "Register a watch for one live PID. The OS validates it and owns the watch lifetime. This does not start, stop or observe an Agent task."));
    const pid = field(watch, "Process ID", { type: "number", min: "1", max: "4294967295", step: "1", placeholder: "Exact live PID" });
    button(watch, "Review process watch...", () => review("watch-pid", { pid: bounded(pid, "PID", 4294967295) }, "Register process watch", "Record a process-exit watch through the existing event service. There is no automatic registration or polling."));
    root.append(watch);
  } else if (app.id === "log") {
    const filters = section("App-local activity log", "This legacy JSONL log lives in the App Host's isolated data directory. It is not the authoritative system audit trail; typed owner-scoped audit-service integration remains pending.");
    const appFilter = field(filters, "App ID filter (optional)", { placeholder: "Exact app ID", autocomplete: "off" });
    const status = choose(filters, "Read status filter", [["", "Any status"], ["ok", "OK"], ["error", "Error"]]);
    const limit = field(filters, "Maximum records", { type: "number", min: "1", max: "1000", step: "1", value: "20" });
    const query = field(filters, "Search text", { placeholder: "Search stored entry text" });
    function base() {
      const args = { limit: bounded(limit, "Record limit") };
      if (appFilter.value.trim()) {
        if (!/^[a-z][a-z0-9_-]*$/.test(appFilter.value.trim())) throw new Error("App filter must be an exact lowercase app ID.");
        args.app = appFilter.value.trim();
      }
      return args;
    }
    button(filters, "Read recent records", (control) => {
      const args = base(); if (status.value) args.status = status.value;
      void request(control, "read", args, (value) => render(value, "Newest first."));
    }, "primary");
    button(filters, "Search log", (control) => {
      if (!query.value.trim()) throw new Error("Enter search text.");
      void request(control, "search", { ...base(), query: query.value }, (value) => render(value, "Stored order. Search does not apply the read status filter."));
    });
    const tail = field(filters, "Tail record count (unfiltered)", { type: "number", min: "1", max: "1000", step: "1", value: "10" });
    button(filters, "Load tail", (control) => void request(control, "tail", { n: bounded(tail, "Tail count") }, (value) => render(value, "Chronological tail; no App or status filter.")));
    const manual = ui.node("details", null, { class: "card stack" });
    manual.append(ui.node("summary", "Record a manual note"), ui.node("p", "Writing needs data.log.write independently of read permission. Notes have source=user and are not chained audit evidence."));
    const message = field(manual, "Manual note", { rows: "4" }, "textarea");
    const level = choose(manual, "Level", [["info", "Info"], ["debug", "Debug"], ["warn", "Warning"], ["error", "Error"]]);
    button(manual, "Review manual entry...", () => {
      if (!message.value.trim()) throw new Error("Enter a non-empty manual note.");
      review("write", { message: message.value, level: level.value }, "Append manual note", "Append one user-authored record to this App-local legacy log. Existing records are not rewritten.");
    });
    root.append(manual);
  } else root.append(ui.node("p", "This identity has no supported event or log interface.", { class: "empty" }));
}).catch((error) => {
  document.getElementById("notice").textContent = `Events UI unavailable: ${error.message}`;
});
