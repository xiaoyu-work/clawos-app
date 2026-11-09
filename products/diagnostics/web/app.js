ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const root = document.getElementById("workspace");
  const notice = document.getElementById("notice");
  let busy = false;
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
  function section(title, text) {
    const card = ui.node("section", null, { class: "card stack" });
    card.append(ui.node("h2", title), ui.node("p", text)); root.append(card); return card;
  }
  function field(parent, label, attributes) {
    const row = ui.node("label", label); const input = ui.node("input", null, attributes);
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
  async function request(control, command, args, done) {
    if (busy) return;
    busy = true;
    try {
      await ui.run(control, () => {
        const tool = ClawApp.tool(app, command);
        if (!tool) throw new Error(`This entry does not declare ${command}.`);
        return ClawApp.call(tool.name, args);
      }, done, notice);
    } finally { busy = false; }
  }
  function integer(input, label, min, max) {
    const value = Number(input.value);
    if (input.value === "" || !Number.isInteger(value) || value < min || value > max) throw new Error(`${label} must be ${min}-${max}.`);
    return value;
  }

  if (app.id === "hardware-center") {
    const summary = section("Hardware inventory", "Read-only OS collectors provide bounded evidence. No hardware query runs on page load, and missing collectors are not reported as healthy devices.");
    button(summary, "Load hardware summary", (control) => void request(control, "summary", {}, (value) => evidence("Hardware summary", value)), "primary");
    const categories = ui.node("div", null, { class: "cards" }); root.append(categories);
    for (const [command, label, description] of [
      ["cpu", "Processor", "Processor inventory and capabilities."],
      ["gpu", "Graphics", "Graphics adapters reported by the provider."],
      ["memory", "Memory", "Physical memory inventory, not a live monitoring subscription."],
      ["storage", "Storage hardware", "Inventory only; no mount, repair or formatting controls."],
      ["thermal", "Thermal", "Available sensor readings; unsupported sensors stay unavailable."],
      ["drivers", "Drivers", "Loaded or available driver evidence; no installation."],
      ["pci", "PCI devices", "Bus inventory from the OS collector."],
      ["usb", "USB inventory", "Read-only inventory; no USB authorization controls."],
    ]) {
      const card = ui.node("section", null, { class: "card stack" });
      card.append(ui.node("h2", label), ui.node("p", description));
      button(card, `Inspect ${label.toLowerCase()}`, (control) => void request(control, command, {}, (value) => evidence(label, value)));
      categories.append(card);
    }
  } else if (app.id === "crash-doctor") {
    const query = section("Find recent crashes", "Crash evidence is sensitive and requires sys.crash:system, independently of hardware observation.");
    const minutes = field(query, "Look back in minutes (up to 7 days)", { type: "number", min: "1", max: "10080", step: "1", value: "60" });
    const limit = field(query, "Maximum records", { type: "number", min: "1", max: "100", step: "1", value: "20" });
    const records = ui.node("div", null, { class: "scroll" });
    const history = section("Crash records", "Select a record locally, then explicitly request its backtrace. Selection does not run a debugger.");
    history.append(records); ui.replace(records, [ui.node("p", "No crash query has been made.", { class: "empty" })]);
    const selected = field(history, "Exact coredump ID", { placeholder: "<32-hex-boot-id>:<pid>:<timestamp-us>", autocomplete: "off" });
    function queryArgs() { return { since_minutes: integer(minutes, "Lookback", 1, 10080), limit: integer(limit, "Record limit", 1, 100) }; }
    function crashes(value) {
      evidence("Recent crash evidence", value);
      const items = value && (Array.isArray(value.crashes) ? value.crashes : Array.isArray(value.coredumps) ? value.coredumps : null);
      if (!items) { ui.replace(records, [ui.node("p", "No structured crash list supplied. Read the returned evidence or enter a known exact coredump ID.", { class: "muted" })]); return; }
      if (items.some((item) => !item || typeof item !== "object" || Array.isArray(item))) throw new Error("The crash service returned an unrecognized coredump record. No debugger request was made.");
      ui.table(records, items, [
        { label: "Coredump", value: (item) => item.id || item.coredump_id || "Not reported" },
        { label: "Program", value: (item) => item.executable || item.comm || "Not reported" },
        { label: "Time", value: (item) => item.timestamp || item.time || "Not reported" },
        { label: "Signal", value: (item) => item.signal ?? "Not reported" },
      ], { label: "Select", run: (item) => { selected.value = item.id || item.coredump_id || ""; evidence("Selected crash record", item); } });
    }
    button(query, "Find crashes", (control) => void request(control, "recent", queryArgs(), crashes), "primary");
    button(query, "Correlate crash evidence", (control) => void request(control, "diagnose", queryArgs(), (value) => evidence("Crash correlation report", value)));
    button(history, "Load backtrace", (control) => {
      const id = selected.value.trim();
      if (!/^[0-9A-Fa-f]{32}:[1-9][0-9]{0,9}:[1-9][0-9]{0,19}$/.test(id)) throw new Error("Use the full boot-id:pid:timestamp-us coredump selector returned by the OS.");
      void request(control, "backtrace", { id }, (value) => evidence(`Backtrace: ${id}`, value));
    });
  } else if (app.id === "netdiag") {
    const local = section("Local network evidence", "Interface and route observation is separate from DNS resolution and exact-host probing. No sockets or probes are opened on page load.");
    button(local, "Load interfaces", (control) => void request(control, "interfaces", {}, (value) => evidence("Network interfaces", value)), "primary");
    button(local, "Load routes", (control) => void request(control, "routes", {}, (value) => evidence("Network routes", value)));
    const probe = section("Diagnose an explicit target", "DNS contacts the resolver. TCP and diagnosis contact the exact host and port through the OS's DNS-pinned probe service; no network configuration is changed.");
    const target = field(probe, "Host or host:port", { placeholder: "example.org:443 or [2001:db8::1]:443", autocomplete: "off" });
    const attempts = field(probe, "TCP attempts (1-5)", { type: "number", min: "1", max: "5", step: "1", value: "3" });
    const timeout = field(probe, "Timeout per attempt in seconds", { type: "number", min: "0.1", max: "30", step: "0.1", value: "5" });
    function targetValue(requirePort) {
      const value = target.value.trim();
      if (!value || value.startsWith("-") || /[\s/\\@#?]/.test(value) || value.includes("://")) throw new Error("Enter a host or host:port, not a URL, path or credentials.");
      if (requirePort) {
        const match = value.match(/^(?:\[[^\]]+\]|[^:]+):([0-9]+)$/);
        if (!match || Number(match[1]) < 1 || Number(match[1]) > 65535) throw new Error("TCP and diagnosis require an explicit port from 1 to 65535. Bracket IPv6 addresses.");
      }
      return value;
    }
    button(probe, "Resolve DNS", (control) => {
      const value = targetValue(false);
      void request(control, "dns", { target: value }, (result) => evidence(`DNS: ${value}`, result));
    });
    button(probe, "Test TCP connection", (control) => {
      const count = integer(attempts, "Attempts", 1, 5);
      const seconds = Number(timeout.value);
      if (!Number.isFinite(seconds) || seconds < 0.1 || seconds > 30 || count * Math.round(seconds * 1000) > 20000) throw new Error("Timeout must be 0.1-30 seconds, with attempts x timeout no greater than 20 seconds.");
      const value = targetValue(true);
      void request(control, "tcp", { target: value, attempts: count, timeout: seconds }, (result) => evidence(`TCP probe: ${value}`, result));
    }, "primary");
    button(probe, "Run combined diagnosis", (control) => {
      const value = targetValue(true);
      void request(control, "diagnose", { target: value }, (result) => evidence(`Network diagnosis: ${value}`, result));
    });
    probe.append(ui.node("p", "Combined diagnosis uses the service's bounded defaults; the attempts and timeout fields apply only to Test TCP connection.", { class: "muted small" }));
  } else root.append(ui.node("p", "This identity has no supported diagnostic workflow.", { class: "empty" }));
}).catch((error) => {
  document.getElementById("notice").textContent = `Diagnostics UI unavailable: ${error.message}`;
});
