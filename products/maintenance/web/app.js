ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const root = document.getElementById("workspace");
  const notice = document.getElementById("notice");
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
  function section(title, text) {
    const card = ui.node("section", null, { class: "card stack" });
    card.append(ui.node("h2", title), ui.node("p", text)); root.append(card);
    return card;
  }
  function field(parent, label, placeholder) {
    const row = ui.node("label", label);
    const input = ui.node("input", null, { placeholder, autocomplete: "off" });
    row.append(input); parent.append(row); return input;
  }
  function button(parent, label, action, className = "") {
    const control = ui.node("button", label, { type: "button", class: className });
    control.onclick = () => { try { action(control); } catch (error) { notice.textContent = error.message; } };
    parent.append(control); return control;
  }
  function evidence(title, value) {
    document.getElementById("result-title").textContent = title;
    ui.replace(document.getElementById("result"), [detail(value)]);
  }
  async function request(control, command, args, done, status = notice) {
    if (busy) return;
    busy = true;
    try {
      await ui.run(control, () => {
        const tool = ClawApp.tool(app, command);
        if (!tool) throw new Error(`This identity does not declare ${command}.`);
        return ClawApp.call(tool.name, args);
      }, done, status);
    } finally { busy = false; }
  }
  function review(command, args, title, explanation) {
    if (busy || reviewing) return;
    reviewing = true;
    const dialog = ui.node("dialog");
    const form = ui.node("form");
    const check = ui.node("input", null, { type: "checkbox", required: "" });
    const label = ui.node("label", "I confirm this change to the exact target shown.");
    label.append(check);
    const status = ui.node("p", "", { class: "notice", role: "status", "aria-live": "polite" });
    const cancel = ui.node("button", "Cancel", { type: "button" });
    const execute = ui.node("button", title, { type: "submit", class: "primary" });
    const actions = ui.node("div", null, { class: "toolbar" }); actions.append(cancel, execute);
    form.append(ui.node("p", explanation), detail(args), label, status, actions);
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (!check.checked || busy) return;
      cancel.disabled = true;
      const callArgs = { ...args };
      if (app.id === "config-editor") callArgs.confirm = true;
      await request(execute, command, callArgs, (value) => {
        evidence(`${title}: ${args.unit || args.target}`, value);
        notice.textContent = "Response received. Inspect this target again before another change. No automatic retry.";
        dialog.close();
      }, status);
      cancel.disabled = false;
      check.checked = false;
      if (dialog.open) status.append(ui.node("span", " The effect may be unknown. Inspect current state before retrying."));
    };
    cancel.onclick = () => dialog.close();
    dialog.addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
    dialog.addEventListener("close", () => { reviewing = false; dialog.remove(); });
    dialog.append(ui.node("h2", title), form);
    document.body.append(dialog); dialog.showModal();
  }

  if (app.id === "config-editor") {
    const inspect = section("1. Inspect an exact configuration target", "Only supported canonical targets below /etc are admitted. Inspection itself needs the target's sensitive configuration permission.");
    const target = field(inspect, "Configuration target", "/etc/example.conf");
    function targetPath() {
      const value = target.value.trim();
      if (!value.startsWith("/etc/") || value.includes("\0") || value.split("/").slice(1).some((part) => !part || part === "." || part === "..")) throw new Error("Enter a canonical file path below /etc, without traversal or symlinks.");
      return value;
    }
    button(inspect, "Inspect target", (control) => {
      const args = { target: targetPath() };
      void request(control, "inspect", args, (value) => evidence(`Current configuration: ${args.target}`, value));
    }, "primary");
    const replace = section("2. Validate a staged replacement", "Prepare replacement content in a separate file first. This UI does not write arbitrary text or execute a shell. Validation does not apply the file.");
    const source = field(replace, "Canonical staged source file", "/home/user/staged/example.conf");
    function replacement() {
      const value = source.value.trim();
      if (!value.startsWith("/") || value.includes("\0") || value.length > 4096) throw new Error("Enter an absolute canonical staged source path.");
      return { target: targetPath(), source: value };
    }
    button(replace, "Validate replacement", (control) => {
      const args = replacement();
      void request(control, "validate", args, (value) => evidence(`Validation evidence: ${args.target}`, value));
    }, "primary");
    button(replace, "Review atomic replacement...", () => review("apply", replacement(), "Apply configuration", "Review the validation evidence first. The OS validates supported targets and performs metadata-preserving atomic replacement. Earlier validation cannot prove the source is unchanged."));
    const restore = section("3. Restore a recorded backup", "Use an owner-bound token returned by the OS for this exact target. No backup or rollback availability is assumed.");
    const token = field(restore, "Backup token (32 hexadecimal characters)", "Exact token from a prior operation");
    button(restore, "Review restore...", () => {
      if (!/^[0-9a-fA-F]{32}$/.test(token.value.trim())) throw new Error("Backup token must contain exactly 32 hexadecimal characters.");
      review("restore", { target: targetPath(), backup_token: token.value.trim() }, "Restore configuration", "Replace the selected target with its recorded backup. The OS checks token ownership and applicability.");
    });
  } else if (app.id === "systemd") {
    const inspect = section("Inspect a service unit", "No unit discovery, shell command or broad service grant is implied. Enter the exact unit, including its suffix.");
    const unit = field(inspect, "Exact systemd unit", "example.service");
    function unitName() {
      const value = unit.value.trim();
      if (value.length > 255 || !/^[A-Za-z0-9_][A-Za-z0-9_.@:-]*\.(service|socket|timer|mount|target|path)$/.test(value)) throw new Error("Use a valid exact .service, .socket, .timer, .mount, .target or .path unit name.");
      return value;
    }
    button(inspect, "Inspect unit", (control) => {
      const args = { unit: unitName() };
      void request(control, "status", args, (value) => evidence(`Unit state: ${args.unit}`, value));
    }, "primary");
    const lifecycle = section("Runtime lifecycle", "These actions need separate sys.service authority for the exact unit. Restart and reload do not promise reversible rollback.");
    for (const [command, label, explanation] of [
      ["start", "Start unit", "Start this exact unit. Dependencies may also be affected by systemd."],
      ["stop", "Stop unit", "Stop this exact unit. Dependent work or service availability may be interrupted."],
      ["restart", "Restart unit", "Restart can interrupt active work. It is not a reversible operation."],
      ["reload", "Reload unit", "Ask the unit to reload its configuration. This does not edit or validate configuration files."],
    ]) button(lifecycle, `${label}...`, () => review(command, { unit: unitName() }, label, explanation));
    const boot = section("Boot enablement", "Enablement is separate from the current runtime state. Enabling does not mean the unit is now running, and disabling is not a stop request.");
    button(boot, "Enable unit...", () => review("enable", { unit: unitName() }, "Enable unit", "Change this unit's enablement through the OS service."));
    button(boot, "Disable unit...", () => review("disable", { unit: unitName() }, "Disable unit", "Remove this unit's enablement through the OS service; do not infer its active state."));
  } else {
    root.append(ui.node("p", "This entry has no supported maintenance workflow.", { class: "empty" }));
  }
}).catch((error) => {
  document.getElementById("notice").textContent = `Maintenance UI unavailable: ${error.message}`;
});
