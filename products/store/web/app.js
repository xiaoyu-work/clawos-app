ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const $ = (selector) => document.querySelector(selector);
  const has = (command) => Boolean(ClawApp.tool(app, command));
  const pkg = app.id === "pkg";
  let busy = false;
  let entries = [];
  let selected = null;
  let generation = 0;
  let inventory = false;
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
    $("#installed").disabled = busy || !has(pkg ? "list" : "installed");
    $("#availability").disabled = busy || !selected?.ready || !has("has");
    $("#desktop").disabled = busy || !selected?.ready || !has("open");
    for (const button of $("#actions").querySelectorAll("button")) button.disabled = busy || !selected?.ready;
    for (const button of $("#maintenance").querySelectorAll("button")) button.disabled = busy;
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
    $("#package-name").textContent = "Select a package";
    $("#summary").textContent = "";
    $("#description").textContent = "";
    $("#availability-state").textContent = "";
    $("#metadata").replaceChildren();
    update();
  }
  function renderEntries() {
    const filter = $("#filter").value.trim().toLowerCase();
    const visible = entries.filter((entry) => `${entry.name} ${entry.summary || ""}`.toLowerCase().includes(filter));
    $("#count").textContent = `${visible.length} / ${entries.length} loaded`;
    const version = generation;
    ui.replace($("#packages"), visible.map((entry) => {
      const button = ui.node("button", `${entry.name}${entry.summary ? `\n${entry.summary}` : ""}`, {
        type: "button", class: "prose", "data-package": entry.name,
      });
      button.onclick = () => { if (!busy && version === generation) select(entry.name); };
      return button;
    }));
    if (!visible.length) ui.replace($("#packages"), [ui.node("p",
      entries.length ? "No loaded results match this filter." : "No packages returned. Search the catalog or load inventory.", { class: "empty" })]);
  }
  function browse(loadInventory) {
    if (busy) return;
    clearSelection();
    entries = [];
    inventory = loadInventory;
    $("#filter").value = "";
    $("#list-title").textContent = inventory ? "Installed / package inventory" : "Catalog matches";
    $("#inventory-help").textContent = inventory ?
      "Read-only OS snapshot of packages reported installed by dpkg. Catalog versions and pending transactions are separate." : "";
    $("#packages").replaceChildren(ui.node("p", "Loading packages...", { class: "empty" }));
    const command = inventory ? pkg ? "list" : "installed" : "search";
    const args = inventory ? {} : { query: pkg ? [$("#query").value] : $("#query").value, limit: Number($("#limit").value) };
    void perform(() => call(command, args), (value) => {
      const rows = inventory ? value.packages : value.results;
      if (!Array.isArray(rows)) throw new Error("The backend returned no package list.");
      entries = rows.map((row) => typeof row === "string" ? { name: row } : row).filter((row) => typeof row.name === "string");
      renderEntries();
      $("#outcome").textContent = value.truncated ? value.hint || "The backend bounded these search results; refine the query or increase the limit." :
        `${entries.length} package names returned. Select one to read its metadata.`;
    }, () => {
      $("#packages").replaceChildren(ui.node("p", "Package data is unavailable. See the error above; no empty catalog or inventory is inferred.", { class: "empty" }));
      $("#count").textContent = "";
    });
  }
  function select(name) {
    if (busy) return;
    selected = { name };
    $("#package-name").textContent = name;
    $("#summary").textContent = "Loading package metadata...";
    $("#description").textContent = "";
    $("#metadata").replaceChildren();
    $("#availability-state").textContent = "";
    const version = generation;
    for (const button of $("#packages").querySelectorAll("button")) button.classList.toggle("selected", button.dataset.package === name);
    void perform(() => call("show", { name }), (value) => {
      if (version !== generation || selected?.name !== name) return;
      if (value.found !== true) { selected = null; throw new Error("Package metadata was not found. No transaction is enabled."); }
      selected = { ...value, name, ready: true };
      $("#summary").textContent = value.summary || "No summary provided.";
      $("#description").textContent = value.description || "";
      const fields = [];
      for (const [label, text] of [
        ["Version in catalog", value.version], ["Section", value.section], ["Dependencies", value.depends],
        ["Installed size (KiB)", value.installed_size], ["Homepage (metadata only)", value.homepage], ["Maintainer", value.maintainer],
      ]) {
        if (text) fields.push(ui.node("dt", label), ui.node("dd", text));
      }
      ui.replace($("#metadata"), fields);
    }, () => {
      selected = null;
      $("#summary").textContent = "Package metadata could not be loaded. No transaction target is enabled.";
    });
  }
  const transactions = [
    ["need", "Install if missing", "Requests installation only if the backend does not consider the selected package present."],
    ["upgrade", "Upgrade package", "Requests an upgrade of this exact package and any dependencies selected by the system package resolver."],
    ["install-version", "Install exact version", "Requests the exact package version below; this may upgrade or downgrade it."],
    ["remove", "Remove package", "Removes the selected system package. Dependencies and running programs may be affected."],
    ["purge", "Purge package and configuration", "Removes the selected package and its system configuration. This is more destructive than Remove."],
    ["hold", "Hold package version", "Requests a package hold, which affects future system upgrades."],
    ["unhold", "Release package hold", "Releases this package's version hold."],
    ["update", "Refresh package indexes", "Refreshes system-wide package indexes. This is not a catalog-only read."],
    ["upgrade-all", "Upgrade the entire system", "Requests upgrades across the whole system, including packages not selected on this page."],
  ];
  function renderTransaction(value, command, name) {
    const items = [ui.node("h3", `${transactions.find((item) => item[0] === command)[1]} - ${name || "system-wide"}`, { class: "prose" })];
    if (command === "need" && Array.isArray(value.installed) && Array.isArray(value.already_present) && Array.isArray(value.failed)) {
      items.push(ui.node("p", `${value.installed.length} installed; ${value.already_present.length} already present; ${value.failed.length} failed.`));
      for (const [label, packages] of [["Installed by backend", value.installed], ["Already present", value.already_present], ["Failed", value.failed]]) {
        for (const packageName of packages) items.push(ui.node("p",
          `${label}: ${packageName}${value.errors?.[packageName] ? ` - ${value.errors[packageName]}` : ""}`, { class: label === "Failed" ? "danger" : "prose" }));
      }
      $("#outcome").textContent = value.failed.length ? "Installation request has failures; do not treat this as complete success." :
        value.installed.includes(name) || value.already_present.includes(name) ?
          "Backend reported package installation/presence. Reload inventory or check availability for a fresh observation." :
          "No final installation/presence result was reported for the selected package. Inspect state before another request.";
    } else {
      items.push(ui.node("p", value.ok === true ? "The broker returned ok. This is not independent verification of the resulting system state." :
        "Broker response received. No final success is inferred from an unclassified response."));
      const fields = [];
      for (const [label, text] of [
        ["Reported status", value.status], ["Transaction ID", value.transaction_id], ["Mutation ID", value.mutation_id],
        ["Reported action", value.action], ["Exit code", value.exit_code],
        ["Installed after", value.after?.installed], ["Version after", value.after?.version],
        ["Held after", value.after?.held], ["Installed before", value.before?.installed], ["Version before", value.before?.version],
      ]) {
        if (text !== undefined && text !== null) fields.push(ui.node("dt", label), ui.node("dd", text));
      }
      const details = ui.node("dl", null, { class: "detail-grid" });
      details.append(...fields);
      items.push(details);
      if (value.stderr_tail) items.push(ui.node("pre", value.stderr_tail, { class: "danger" }));
      if (value.stdout_tail) items.push(ui.node("pre", value.stdout_tail));
      $("#outcome").textContent = "Transaction response received. Review its reported status; no automatic retry or rollback is performed.";
    }
    ui.replace($("#result"), items);
  }
  function transaction(command) {
    if (busy || !has(command)) return;
    const systemWide = command === "update" || command === "upgrade-all";
    const target = selected;
    if (!systemWide && !target?.ready) return;
    const version = generation;
    const [, title, description] = transactions.find((item) => item[0] === command);
    const dialog = ui.node("dialog");
    dialog.append(ui.node("h2", title), ui.node("p", `${description} Requires the owning App's live Critical package authority; this confirmation grants nothing.`));
    const form = ui.node("form");
    form.append(ui.node("p", `Exact target: ${systemWide ? "the system package manager" : target.name}`, { class: "code" }));
    let versionInput;
    if (command === "install-version") {
      const label = ui.node("label", "Exact Debian version");
      versionInput = ui.node("input", null, { required: "", pattern: "[A-Za-z0-9][A-Za-z0-9.:+~\\-]{0,254}" });
      versionInput.value = target.version || "";
      label.append(versionInput);
      form.append(label);
    }
    const label = ui.node("label", `I reviewed this ${systemWide ? "system-wide" : "exact-package"} transaction and want to request it once.`);
    const confirm = ui.node("input", null, { type: "checkbox", required: "" });
    label.append(confirm);
    const actions = ui.node("div", null, { class: "toolbar" });
    const cancel = ui.node("button", "Cancel", { type: "button" });
    const submit = ui.node("button", title, { type: "submit", class: ["remove", "purge", "upgrade-all"].includes(command) ? "danger" : "primary" });
    cancel.onclick = () => dialog.close();
    actions.append(cancel, submit);
    form.append(label, actions);
    form.onsubmit = (event) => {
      event.preventDefault();
      if (busy || !form.reportValidity() || version !== generation || !systemWide && selected !== target) return;
      const name = target?.name;
      const args = systemWide ? {} : command === "need" ? { packages: [name] } : { package: name };
      if (versionInput) args.version = versionInput.value;
      clearSelection();
      entries = [];
      $("#packages").replaceChildren(ui.node("p", "Refresh catalog or inventory before selecting another transaction target.", { class: "empty" }));
      $("#count").textContent = "";
      $("#result").replaceChildren(ui.node("p", "Transaction requested once. Until confirmed, its outcome is unknown.", { class: "notice" }));
      $("#outcome").textContent = "System transaction pending. A timeout does not mean that no changes occurred.";
      void perform(() => call(command, args), (value) => renderTransaction(value, command, systemWide ? "" : name), () => {
        $("#result").replaceChildren(ui.node("p", "Transaction failed or has an unknown outcome. See the error above and inspect authoritative state before requesting it again.", { class: "danger" }));
        $("#outcome").textContent = "No final transaction result confirmed; no automatic retry or rollback.";
      })
        .finally(() => dialog.close());
    };
    dialog.append(form);
    dialog.addEventListener("close", () => dialog.remove());
    document.body.append(dialog);
    dialog.showModal();
  }

  $("#search").onsubmit = (event) => { event.preventDefault(); if ($("#search").reportValidity()) browse(false); };
  $("#installed").onclick = () => browse(true);
  $("#filter").oninput = () => { if (!busy) renderEntries(); };
  $("#availability").hidden = !has("has");
  $("#availability").onclick = () => {
    if (!selected) return;
    const name = selected.name;
    const version = generation;
    void perform(() => call("has", { name }), (value) => {
      if (version !== generation || selected?.name !== name) return;
      $("#availability-state").textContent = value.available === true ?
        value.type === "system" ? `Backend reports installed via dpkg: ${name}.` :
          `Command availability only, not package installation: ${value.details || name}` :
        `Backend reports unavailable: ${value.details || name}`;
    });
  };
  $("#desktop").hidden = !has("open");
  $("#desktop").onclick = () => {
    if (!selected || busy) return;
    const name = selected.name;
    ui.command(app, "open", { name }, (value) => {
      checked(value);
      ui.replace($("#result"), [ui.node("p", value.opened === true ? `Native Store activation reported for ${name}. No installation requested.` :
        "Native activation was not confirmed.")]);
    }, { title: "Open the selected package in the native Store", submitLabel: "Open native Store",
      description: "Explicit desktop activation of this same product. This Web entry receives no native package transaction authority.",
      fields: { name: { readOnly: true } } });
  };
  for (const [command, label] of transactions) {
    if (!pkg || !has(command)) continue;
    const button = ui.node("button", label, { type: "button" });
    button.onclick = () => transaction(command);
    (["update", "upgrade-all"].includes(command) ? $("#maintenance") : $("#actions")).append(button);
  }
  $("#system-actions").hidden = !$("#maintenance").children.length;
  $("#scope").textContent = pkg ?
    "This package-management entry can request separately authorized system transactions. Every mutation is explicitly reviewed; browsing never installs anything." :
    "This Store entry exposes catalog, inventory, package details and native activation only. It cannot install, remove or borrow the pkg App's authority.";
  $("#transaction-help").textContent = pkg ?
    "Select and inspect a package first. Each action opens a separate confirmation; confirmations start unchecked and are not capability grants." :
    "Unavailable in this entry: no install/remove/upgrade tools are declared. Native Store activation is separate and never runs automatically.";
  renderEntries();
  update();
});
