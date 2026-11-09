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
      box.append(grid.children.length ? grid : ui.node("p", "No additional evidence returned.", { class: "muted" }));
    }
    return box;
  }
  function evidence(title, value) {
    document.getElementById("result-title").textContent = title;
    ui.replace(document.getElementById("result"), [detail(value)]);
  }
  function section(title, text) {
    const card = ui.node("section", null, { class: "card stack" });
    card.append(ui.node("h2", title), ui.node("p", text)); root.append(card); return card;
  }
  function field(parent, label, attributes = {}) {
    const row = ui.node("label", label);
    const input = ui.node("input", null, attributes);
    row.append(input); parent.append(row); return input;
  }
  function choose(parent, label, choices) {
    const row = ui.node("label", label); const select = ui.node("select");
    for (const [value, text] of choices) select.append(ui.node("option", text, { value }));
    row.append(select); parent.append(row); return select;
  }
  function button(parent, label, action, className = "") {
    const control = ui.node("button", label, { type: "button", class: className });
    control.onclick = () => { try { action(control); } catch (error) { notice.textContent = error.message; } };
    parent.append(control); return control;
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
  function token(input, name) {
    const value = input.value.trim();
    if (!/^[0-9a-fA-F]{32}$/.test(value)) throw new Error(`${name} must be exactly 32 hexadecimal characters.`);
    return value;
  }
  function review(command, args, title, explanation, confirm = false) {
    if (busy || reviewing) return;
    reviewing = true;
    const dialog = ui.node("dialog"); const form = ui.node("form");
    const check = ui.node("input", null, { type: "checkbox", required: "" });
    const label = ui.node("label", "I understand the impact and confirm this exact change."); label.append(check);
    const status = ui.node("p", "", { class: "notice", role: "status", "aria-live": "polite" });
    const cancel = ui.node("button", "Cancel", { type: "button" });
    const execute = ui.node("button", title, { type: "submit", class: "danger" });
    const actions = ui.node("div", null, { class: "toolbar" }); actions.append(cancel, execute);
    form.append(ui.node("p", explanation), detail(args), label, status, actions);
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (!check.checked || busy) return;
      cancel.disabled = true;
      await request(execute, command, confirm ? { ...args, confirm: true } : args, (value) => {
        evidence(title, value);
        notice.textContent = "Response received. Reload policy state before another change. No automatic retry.";
        dialog.close();
      }, status);
      cancel.disabled = false;
      check.checked = false;
      if (dialog.open) status.append(ui.node("span", " An interrupted operation may have completed. Inspect state before retrying."));
    };
    cancel.onclick = () => dialog.close();
    dialog.addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
    dialog.addEventListener("close", () => { reviewing = false; dialog.remove(); });
    dialog.append(ui.node("h2", title), form); document.body.append(dialog); dialog.showModal();
  }

  if (app.id === "security-center") {
    const intro = section("Security evidence", "Sensitive, read-only inspection uses sys.security:audit. These reports do not configure the firewall, authorize USB devices or establish a security certification.");
    button(intro, "Load security summary", (control) => void request(control, "summary", {}, (value) => evidence("Security summary", value)), "primary");
    const categories = ui.node("div", null, { class: "cards" }); root.append(categories);
    for (const [command, label, description] of [
      ["auth", "Authentication", "Authentication configuration and evidence."],
      ["ssh", "SSH", "SSH exposure and service configuration evidence."],
      ["sudo", "Privilege delegation", "Inspect sudo-related policy without changing it."],
      ["mac", "Mandatory access control", "Inspect available confinement evidence."],
      ["ports", "Listening ports", "Inspect listening-service exposure."],
      ["events", "Security events", "Read the provider's security-event report."],
    ]) {
      const card = ui.node("section", null, { class: "card stack" });
      card.append(ui.node("h2", label), ui.node("p", description));
      button(card, `Inspect ${label.toLowerCase()}`, (control) => void request(control, command, {}, (value) => evidence(label, value)));
      categories.append(card);
    }
  } else if (app.id === "firewall-manager") {
    const state = section("Managed firewall rules", "Observation is separate from net.firewall:manage. Only the OS-managed rule set is controlled here; no rule is applied on selection.");
    const rules = ui.node("div", null, { class: "scroll" }); state.append(rules);
    ui.replace(rules, [ui.node("p", "Firewall state has not been loaded.", { class: "empty" })]);
    const selected = field(state, "Exact rule ID", { placeholder: "32 hexadecimal characters", autocomplete: "off" });
    button(state, "Load firewall state", (control) => void request(control, "status", {}, (value) => {
      evidence("Firewall status evidence", value);
      const items = value && Array.isArray(value.rules) ? value.rules : null;
      if (!items) { ui.replace(rules, [ui.node("p", "No structured rule list supplied. See the status evidence below.", { class: "muted" })]); return; }
      if (items.some((item) => !item || typeof item !== "object" || Array.isArray(item))) throw new Error("The firewall service returned an unrecognized rule record. No policy change was made.");
      ui.table(rules, items, [
        { label: "Rule", value: (item) => item.rule_id || item.id || "Not reported" },
        { label: "Action", key: "action" }, { label: "Direction", key: "direction" },
        { label: "Protocol / port", value: (item) => `${item.protocol || ""} ${item.port ?? ""}` },
        { label: "Remote", value: (item) => item.remote || "Not restricted by this field" },
      ], { label: "Select", run: (item) => { selected.value = item.rule_id || item.id || ""; evidence("Selected firewall rule (status snapshot)", item); } });
    }), "primary");
    button(state, "Delete selected rule...", () => review("delete", { rule_id: token(selected, "Rule ID") }, "Delete firewall rule", "Removing a rule changes traffic policy immediately and may affect connectivity."));
    const create = section("Add a scoped rule", "Choose the rule's direction, protocol and exact port. An omitted remote or interface is not a restriction.");
    const action = choose(create, "Decision", [["allow", "Allow"], ["deny", "Deny"]]);
    const direction = choose(create, "Direction", [["input", "Incoming"], ["output", "Outgoing"]]);
    const protocol = choose(create, "Protocol", [["tcp", "TCP"], ["udp", "UDP"]]);
    const port = field(create, "Port", { type: "number", min: "1", max: "65535", step: "1", placeholder: "443" });
    const remote = field(create, "Remote CIDR (optional)", { placeholder: "192.0.2.0/24 or 2001:db8::/32", autocomplete: "off" });
    const iface = field(create, "Interface (optional)", { placeholder: "eth0", maxlength: "15", autocomplete: "off" });
    button(create, "Review new rule...", () => {
      const number = Number(port.value);
      if (!Number.isInteger(number) || number < 1 || number > 65535) throw new Error("Port must be an integer from 1 to 65535.");
      const args = { action: action.value, direction: direction.value, protocol: protocol.value, port: number };
      if (remote.value.trim()) args.remote = remote.value.trim();
      if (iface.value.trim()) {
        if (!/^[A-Za-z0-9_.:-]{1,15}$/.test(iface.value.trim())) throw new Error("Interface name is invalid.");
        args.interface = iface.value.trim();
      }
      review("add", args, "Add firewall rule", "The OS validates and normalizes CIDR ranges. Review the full traffic scope; changes can interrupt this session.");
    }, "primary");
    const advanced = ui.node("details", null, { class: "card stack" }); advanced.append(ui.node("summary", "Clear rules or restore a recorded revision"));
    button(advanced, "Clear managed rules...", () => review("clear", {}, "Clear managed firewall rules", "Clear the dedicated App-managed rule set, not just the selected rule. This can change host exposure.", true), "danger");
    const backup = field(advanced, "Owner-bound backup token", { placeholder: "32 hexadecimal characters", autocomplete: "off" });
    button(advanced, "Restore recorded rules...", () => review("restore", { backup_token: token(backup, "Backup token") }, "Restore firewall rules", "The OS checks ownership and rejects a backup superseded by newer revisions. Recovery is not guaranteed.", true));
    root.append(advanced);
  } else if (app.id === "usb-guard") {
    const state = section("USB device policy", "Device observation and device.usb:control are separate. Blocking, ejecting or deauthorizing a device can disconnect storage or input hardware.");
    const devices = ui.node("div", null, { class: "scroll" }); state.append(devices);
    ui.replace(devices, [ui.node("p", "USB devices have not been loaded.", { class: "empty" })]);
    const selected = field(state, "Exact USB sysfs ID", { placeholder: "1-2 or 1-2.3", autocomplete: "off" });
    function device() {
      const value = selected.value.trim();
      if (value.length < 3 || value.length > 64 || !/^[0-9]+-[0-9]+(?:\.[0-9]+)*$/.test(value)) throw new Error("Use an exact USB sysfs device ID, such as 1-2 or 1-2.3.");
      return value;
    }
    button(state, "Load USB state", (control) => void request(control, "status", {}, (value) => {
      evidence("USB status evidence", value);
      const items = value && Array.isArray(value.devices) ? value.devices : null;
      if (!items) { ui.replace(devices, [ui.node("p", "No structured device list supplied. See status evidence below.", { class: "muted" })]); return; }
      if (items.some((item) => !item || typeof item !== "object" || Array.isArray(item))) throw new Error("The USB service returned an unrecognized device record. No control request was made.");
      ui.table(devices, items, [
        { label: "Device", value: (item) => item.device || item.id || "Not reported" },
        { label: "Name", value: (item) => item.product || item.name || "Not reported" },
        { label: "Authorized", value: (item) => item.authorized === undefined ? "Not reported" : String(item.authorized) },
      ], { label: "Select", run: (item) => { selected.value = item.device || item.id || ""; evidence("Selected USB device (status snapshot)", item); } });
    }), "primary");
    const controls = section("Selected device actions", "Selection alone is inert. Authorization on deliberately omits the deauthorization confirmation flag.");
    button(controls, "Authorize device...", () => review("authorize", { device: device(), state: "on" }, "Authorize USB device", "Allow this exact device through the OS authorization service."));
    button(controls, "Deauthorize device...", () => review("authorize", { device: device(), state: "off" }, "Deauthorize USB device", "This can disconnect the device. Protected mounts and OS safety checks may refuse the operation.", true), "danger");
    button(controls, "Block device...", () => review("block", { device: device() }, "Block USB device", "Create a durable OS-managed block for this device. Existing device access may be interrupted.", true), "danger");
    button(controls, "Eject device...", () => review("eject", { device: device() }, "Eject USB device", "The OS revalidates the device and protected storage before power-off. Wait for confirmed evidence before removal.", true), "danger");
    const recovery = ui.node("details", null, { class: "card stack" }); recovery.append(ui.node("summary", "Unblock or restore recorded USB policy"));
    const rule = field(recovery, "Exact block rule ID", { placeholder: "32 hexadecimal characters", autocomplete: "off" });
    button(recovery, "Unblock rule...", () => review("unblock", { rule_id: token(rule, "Rule ID") }, "Unblock USB rule", "Remove this exact durable blocking rule, not every rule for a device.", true));
    const backup = field(recovery, "Owner-bound backup token", { placeholder: "32 hexadecimal characters", autocomplete: "off" });
    button(recovery, "Restore USB policy...", () => review("restore", { backup_token: token(backup, "Backup token") }, "Restore USB policy", "Restore only if the OS accepts this owner/revision-bound backup token.", true));
    root.append(recovery);
  } else root.append(ui.node("p", "This identity has no supported security workflow.", { class: "empty" }));
}).catch((error) => {
  document.getElementById("notice").textContent = `Security UI unavailable: ${error.message}`;
});
