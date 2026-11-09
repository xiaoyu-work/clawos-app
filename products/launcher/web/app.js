ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const $ = (selector) => document.querySelector(selector);
  const has = (command) => Boolean(ClawApp.tool(app, command));
  const native = app.id === "cosmic-launcher";
  let busy = false;
  let selected = null;
  let generation = 0;
  ui.showApp(app);

  function call(command, args = {}) {
    const tool = ClawApp.tool(app, command);
    if (!tool) throw new Error(`This entry does not declare ${command}.`);
    return ClawApp.call(tool.name, args);
  }
  function checked(value) {
    ui.output($("#raw"), value);
    if (value && value.error) throw new Error(String(value.error));
    return value;
  }
  function update() {
    $("#launch").disabled = busy || !selected || !has("open");
    $("#running").disabled = busy || !selected || !has("is-running");
    $("#recent").disabled = busy || !has("recent");
    $("#all").disabled = busy || !has("list");
  }
  async function perform(action, render, failed) {
    if (busy) return;
    busy = true;
    const controls = Array.from(document.querySelectorAll("button, input")).filter((control) => !control.disabled);
    controls.forEach((control) => { control.disabled = true; });
    const result = await ui.run(null, async () => checked(await action()), render, $("#notice"));
    if (result === undefined && failed) failed();
    busy = false;
    controls.forEach((control) => { control.disabled = false; });
    update();
  }
  function clearSelection() {
    generation++;
    selected = null;
    $("#selected-name").textContent = "Select an application";
    $("#selected-id").textContent = "";
    $("#description").textContent = "";
    $("#metadata").replaceChildren();
    $("#running-state").textContent = "";
    update();
  }
  function select(entry, recent) {
    if (busy) return;
    selected = entry;
    generation++;
    $("#selected-name").textContent = entry.name || entry.app_id;
    $("#selected-id").textContent = entry.app_id;
    $("#description").textContent = entry.comment || (recent ? "Recent launch record. The backend verifies that the AppID is still installed when launching." : "No description provided.");
    $("#running-state").textContent = "";
    const metadata = [];
    for (const [label, value] of [
      ["Generic name", entry.generic_name], ["Categories", entry.categories], ["Keywords", entry.keywords],
      ["Visibility", entry.hidden ? "Hidden" : entry.no_display ? "NoDisplay" : recent ? "Not reported by recent history" : "Visible"],
      ["Terminal entry", entry.terminal === undefined ? "" : entry.terminal ? "Yes" : "No"],
      ["Last launch", entry.last_launched_at], ["Recent count", entry.count],
    ]) {
      if (value === undefined || value === "") continue;
      metadata.push(ui.node("dt", label), ui.node("dd", value));
    }
    ui.replace($("#metadata"), metadata);
    for (const button of $("#apps").querySelectorAll("button")) button.classList.toggle("selected", button.dataset.appId === entry.app_id);
    update();
  }
  function render(value, mode) {
    const entries = mode === "recent" ? value.recent : mode === "find" ? value.matches : value.apps;
    if (!Array.isArray(entries)) throw new Error("The backend returned no application list.");
    $("#list-title").textContent = mode === "recent" ? "Recent launches by this entry" : mode === "find" ? "Search matches" : "Installed desktop entries";
    $("#count").textContent = `${entries.length} entries`;
    ui.replace($("#apps"), entries.map((entry) => {
      const button = ui.node("button", `${entry.name || entry.app_id}\n${entry.app_id}${entry.comment ? `\n${entry.comment}` : ""}`, {
        type: "button", "data-app-id": entry.app_id,
      });
      button.classList.add("prose");
      button.onclick = () => select(entry, mode === "recent");
      return button;
    }));
    if (!entries.length) ui.replace($("#apps"), [ui.node("p",
      mode === "recent" ? "No recent launches in this entry's own journal." : "No applications match this request.", { class: "empty" })]);
  }
  function browse(mode) {
    if (busy) return;
    clearSelection();
    $("#apps").replaceChildren(ui.node("p", "Loading applications...", { class: "empty" }));
    let args = {};
    if (mode === "find") args = { query: $("#query").value, limit: Number($("#limit").value) };
    if (mode === "recent") args.limit = 20;
    if (mode === "list") {
      args.include_hidden = $("#hidden").checked;
      if (!native) args.include_no_display = $("#no-display").checked;
    }
    void perform(() => call(mode, args), (value) => render(value, mode), () => {
      $("#apps").replaceChildren(ui.node("p", "Could not load applications. See the service error above; no empty catalog is inferred.", { class: "empty" }));
      $("#count").textContent = "";
    });
  }
  function lines(value) {
    return value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  }

  $("#search").onsubmit = (event) => {
    event.preventDefault();
    if (!$("#search").reportValidity()) return;
    browse($("#query").value.trim() ? "find" : "list");
  };
  $("#all").onclick = () => browse("list");
  $("#recent").onclick = () => browse("recent");
  $("#no-display-option").hidden = native;
  $("#running").hidden = !has("is-running");
  $("#running").onclick = () => {
    if (!selected || busy) return;
    const id = selected.app_id;
    const version = generation;
    void perform(() => call("is-running", { app_id: id }), (value) => {
      if (version !== generation || value.app_id !== id) return;
      if (!Array.isArray(value.pids)) throw new Error("No process observation was returned.");
      $("#running-state").textContent = value.running ? `Observed matching PIDs: ${value.pids.join(", ")}. Process-name observation is not an application lifetime guarantee.` :
        "No matching process was observed.";
    });
  };
  $("#launch").onclick = () => {
    if (!selected || busy) return;
    const target = selected;
    const version = generation;
    ui.command(app, "open", native ? { app_id: target.app_id, extras: [] } : { app_id: target.app_id, uri: [], path: [] }, (value) => {
      checked(value);
      if (version !== generation || selected !== target) return;
      $("#outcome").textContent = value.launched === true && value.app_id === target.app_id ?
        `OS reported launch of ${value.name || target.name || target.app_id}${value.launched_at ? ` at ${value.launched_at}` : ""}.` :
        "The launch outcome was not confirmed. Check recent history or running state before trying again.";
    }, {
      title: "Launch the selected application", submitLabel: "Launch through the OS",
      description: "Review this exact AppID and optional targets. Only absolute non-file URIs and existing authorized local files are supported; raw Exec arguments are not accepted. An unknown result must not be blindly retried.",
      fields: { app_id: { label: "Desktop AppID", readOnly: true },
        uri: { label: "Optional absolute non-file URIs (one per line)", format: (values) => values.join("\n"), parse: lines, allowEmpty: true },
        path: { label: "Optional authorized absolute local files (one per line)", type: "textarea", format: (values) => values.join("\n"), parse: lines, allowEmpty: true },
        extras: { label: "Optional ordered absolute local files / non-file URIs (one per line)", format: (values) => values.join("\n"), parse: lines, allowEmpty: true } },
    });
  };
  update();
  if (has("list")) browse("list");
});
