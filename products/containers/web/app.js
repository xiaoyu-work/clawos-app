ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const $ = (id) => document.getElementById(id);
  ui.showApp(app);
  let busy = false;
  let reviewing = false;
  let generation = 0;
  const identifier = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$/;

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
  function context(withTarget = false) {
    const args = { runtime: $("runtime").value };
    if (args.runtime === "containerd") {
      if (!identifier.test($("namespace").value.trim())) throw new Error("containerd requires an exact namespace.");
      args.namespace = $("namespace").value.trim();
    }
    if (withTarget) {
      args.target = $("target").value.trim();
      if (!identifier.test(args.target)) throw new Error("Enter or select a valid container ID or name.");
    }
    return args;
  }
  function evidence(title, value) {
    $("result-title").textContent = title;
    ui.replace($("result"), [detail(value)]);
  }
  async function request(button, command, args, done, notice = $("notice")) {
    if (busy) return;
    busy = true;
    const version = generation;
    try {
      await ui.run(button, () => {
        const tool = ClawApp.tool(app, command);
        if (!tool) throw new Error(`This App does not declare ${command}.`);
        return ClawApp.call(tool.name, args);
      }, (value) => { if (version === generation) done(value); }, notice);
    } finally { busy = false; }
  }
  function reset() {
    generation++;
    $("namespace-label").hidden = $("runtime").value !== "containerd";
    $("namespace").required = $("runtime").value === "containerd";
    $("target").value = "";
    ui.replace($("containers"), [ui.node("p", "Load inventory for the selected runtime. Docker, rootless Podman and rootful Podman are distinct targets.", { class: "empty" })]);
    evidence("Container evidence", "No container selected for this runtime.");
  }
  function inventory(value) {
    const items = value && (Array.isArray(value.containers) ? value.containers : Array.isArray(value.items) ? value.items : null);
    if (!items) {
      ui.replace($("containers"), [ui.node("p", "No structured container list was supplied. A known container ID can still be entered below.", { class: "muted" }), detail(value)]);
      return;
    }
    if (items.some((item) => !item || typeof item !== "object" || Array.isArray(item))) throw new Error("The runtime returned an unrecognized container record. No lifecycle action was taken.");
    if (!items.length) {
      ui.replace($("containers"), [ui.node("p", "No containers returned for this runtime and namespace.", { class: "empty" })]);
      return;
    }
    ui.table($("containers"), items, [
      { label: "Name / ID", value: (item) => item.name || (Array.isArray(item.names) ? item.names.join(", ") : item.names) || item.id || "Not reported" },
      { label: "Image", value: (item) => item.image || "Not reported" },
      { label: "State", value: (item) => item.state || item.status || "Not reported" },
    ], { label: "Select", run: (item) => {
      $("target").value = item.id || item.name || "";
      evidence("Selected inventory record (not a fresh inspection)", item);
    } });
  }
  function observe(button, command) {
    try {
      const args = context(true);
      if (command === "logs") {
        args.lines = Number($("lines").value);
        if (!Number.isInteger(args.lines) || args.lines < 1 || args.lines > 1000) throw new Error("Log lines must be an integer from 1 to 1000.");
      }
      void request(button, command, args, (value) => evidence(`${command === "logs" ? "Recent logs" : button.textContent}: ${args.target}`, value));
    } catch (error) { $("notice").textContent = error.message; }
  }
  function review(command, label) {
    if (busy || reviewing) return;
    let args;
    try {
      args = context(true);
      if (command === "kill") args.signal = $("signal").value;
    } catch (error) { $("notice").textContent = error.message; return; }
    reviewing = true;
    const dialog = ui.node("dialog");
    const form = ui.node("form");
    const check = ui.node("input", null, { type: "checkbox", required: "" });
    const acknowledgment = ui.node("label", `I confirm ${label.toLowerCase()} for this container.`);
    acknowledgment.append(check);
    const notice = ui.node("p", "", { class: "notice", role: "status", "aria-live": "polite" });
    const cancel = ui.node("button", "Cancel", { type: "button" });
    const execute = ui.node("button", label, { type: "submit", class: command === "remove" || command === "kill" ? "danger" : "primary" });
    const actions = ui.node("div", null, { class: "toolbar" }); actions.append(cancel, execute);
    form.append(detail(args), ui.node("p", command === "remove" ?
      "Removal is destructive. No recovery or volume backup is promised." :
      command === "kill" ? "The selected signal is sent to the container. This can interrupt work." :
      "This changes the container lifecycle and can interrupt its workloads. State shown elsewhere may be stale."),
    acknowledgment, notice, actions);
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (!check.checked || busy) return;
      cancel.disabled = true;
      const callArgs = { ...args };
      if (command === "remove") callArgs.confirm = true;
      await request(execute, command, callArgs, (value) => {
        evidence(`${label}: ${args.target}`, value);
        $("notice").textContent = "Response received. Reload inventory before another change. No automatic retry.";
        dialog.close();
      }, notice);
      cancel.disabled = false;
      check.checked = false;
      if (dialog.open) notice.append(ui.node("span", " Inspect current state before retrying; the outcome may be unknown."));
    };
    cancel.onclick = () => dialog.close();
    dialog.addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
    dialog.addEventListener("close", () => { reviewing = false; dialog.remove(); });
    dialog.append(ui.node("h2", `${label}?`), form);
    document.body.append(dialog);
    dialog.showModal();
  }
  $("runtime").onchange = reset;
  $("namespace").oninput = reset;
  $("inventory-form").onsubmit = (event) => {
    event.preventDefault();
    try { void request($("refresh"), "list", context(), inventory); } catch (error) { $("notice").textContent = error.message; }
  };
  $("status").onclick = (event) => void request(event.currentTarget, "status", {}, (value) => evidence("Runtime availability reported by the OS", value));
  for (const name of ["inspect", "logs", "processes", "stats", "namespaces"]) {
    $(name).onclick = (event) => observe(event.currentTarget, name);
  }
  for (const name of ["start", "stop", "restart", "pause", "unpause", "kill", "remove"]) {
    $(name).onclick = (event) => review(name, event.currentTarget.textContent.replace("...", ""));
  }
  reset();
  if (app.id !== "container-manager") ui.replace($("workspace"), [ui.node("p", "This entry has no Container Manager interface.", { class: "empty" })]);
}).catch((error) => {
  document.getElementById("notice").textContent = `Container UI unavailable: ${error.message}`;
});
