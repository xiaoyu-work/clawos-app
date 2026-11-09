ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const root = document.getElementById("workspace");
  const notice = document.getElementById("notice");
  const list = ui.node("div", null, { class: "scroll" });
  let busy = false;
  let reviewing = false;
  let repositoryVersion = 0;
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
    document.getElementById("result-title").textContent = title;
    ui.replace(document.getElementById("result"), [detail(value)]);
  }
  function section(title, text) {
    const card = ui.node("section", null, { class: "card stack" });
    card.append(ui.node("h2", title), ui.node("p", text));
    root.append(card);
    return card;
  }
  function field(parent, label, attributes = {}) {
    const row = ui.node("label", label);
    const input = ui.node("input", null, attributes);
    row.append(input); parent.append(row);
    return input;
  }
  function button(parent, label, action, className = "") {
    const element = ui.node("button", label, { type: "button", class: className });
    element.onclick = () => {
      try { action(element); } catch (error) { notice.textContent = error.message; }
    };
    parent.append(element);
    return element;
  }
  function absolute(value, label) {
    if (!value.startsWith("/") || value.includes("\0") || value.length > 4096) throw new Error(`${label} must be an absolute canonical Linux path.`);
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
  function review(command, args, title, explanation) {
    if (busy || reviewing) return;
    reviewing = true;
    const dialog = ui.node("dialog");
    const form = ui.node("form");
    const check = ui.node("input", null, { type: "checkbox", required: "" });
    const acknowledgment = ui.node("label", "I understand the operation and confirm these exact targets.");
    acknowledgment.append(check);
    const status = ui.node("p", "", { class: "notice", role: "status", "aria-live": "polite" });
    const actions = ui.node("div", null, { class: "toolbar" });
    const cancel = ui.node("button", "Cancel", { type: "button" });
    const execute = ui.node("button", title, { type: "submit", class: ["forget", "retention", "delete", "rollback"].includes(command) ? "danger" : "primary" });
    actions.append(cancel, execute);
    form.append(ui.node("p", explanation), detail(args), acknowledgment, status, actions);
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (!check.checked || busy) return;
      cancel.disabled = true;
      const callArgs = { ...args };
      if (["restore", "forget", "retention", "rollback"].includes(command)) callArgs.confirm = true;
      await request(execute, command, callArgs, (value) => {
        evidence(title, value);
        notice.textContent = "Response received. Reload snapshots or inspect status before another operation. No automatic retry.";
        dialog.close();
      }, status);
      cancel.disabled = false;
      check.checked = false;
      if (dialog.open) status.append(ui.node("span", " An interrupted request may have completed. Check state before retrying."));
    };
    cancel.onclick = () => dialog.close();
    dialog.addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
    dialog.addEventListener("close", () => { reviewing = false; dialog.remove(); });
    dialog.append(ui.node("h2", title), form);
    document.body.append(dialog); dialog.showModal();
  }
  function renderSnapshots(value, selection) {
    const items = value && (Array.isArray(value.snapshots) ? value.snapshots : Array.isArray(value.items) ? value.items : null);
    if (!items) {
      ui.replace(list, [ui.node("p", "The service did not supply a structured snapshot list. Inspect its evidence or enter a known exact ID.", { class: "muted" }), detail(value)]);
      return;
    }
    if (items.some((item) => !item || typeof item !== "object" || Array.isArray(item))) throw new Error("The service returned an unrecognized snapshot record. No recovery action was taken.");
    if (!items.length) { ui.replace(list, [ui.node("p", "No snapshots returned for this source.", { class: "empty" })]); return; }
    ui.table(list, items, [
      { label: "Snapshot ID", value: (item) => item.id || item.short_id || "Not reported" },
      { label: "Created", value: (item) => item.time || item.created_at || "Not reported" },
      { label: "Description / tags", value: (item) => item.description || (Array.isArray(item.tags) ? item.tags.join(", ") : item.tags) || "Not reported" },
    ], { label: "Select", run: (item) => {
      selection.value = item.id || item.short_id || "";
      evidence("Selected snapshot record (not a restore preview)", item);
    } });
  }

  if (app.id === "backup-center") {
    const repoCard = section("Local backup repository", "Choose a mounted, canonical local Restic repository and an OS credential reference. Passwords are never entered here.");
    const repo = field(repoCard, "Repository path", { placeholder: "/mnt/backups/restic", autocomplete: "off" });
    const credential = field(repoCard, "Credential reference (namespace/name)", { placeholder: "backups/restic", autocomplete: "off" });
    const repoActions = ui.node("div", null, { class: "toolbar" }); repoCard.append(repoActions);
    function repository() {
      if (!/^[A-Za-z0-9_.:-]+\/[A-Za-z0-9_.:-]+$/.test(credential.value.trim())) throw new Error("Use a stored credential reference in namespace/name form, not a password.");
      return { repo: absolute(repo.value.trim(), "Repository"), credential: credential.value.trim() };
    }
    const history = section("Repository snapshots", "Loading snapshots does not create, restore or remove data.");
    history.append(list); ui.replace(list, [ui.node("p", "No repository has been loaded.", { class: "empty" })]);
    const selected = field(history, "Snapshot ID", { placeholder: "Select an exact snapshot ID; latest is allowed only for restore", autocomplete: "off" });
    function snapshot(allowLatest) {
      const value = selected.value.trim();
      if (!(allowLatest && value === "latest") && !/^[0-9a-fA-F]{8,64}$/.test(value)) throw new Error("Select an exact 8-64 hexadecimal snapshot ID." + (allowLatest ? " Restore also accepts latest." : ""));
      return value;
    }
    const invalidate = () => {
      repositoryVersion++;
      selected.value = "";
      ui.replace(list, [ui.node("p", "Repository or credential changed. Load snapshots again.", { class: "empty" })]);
    };
    repo.oninput = invalidate; credential.oninput = invalidate;
    button(repoActions, "Load snapshots", (control) => {
      const args = repository(); const version = repositoryVersion;
      void request(control, "snapshots", args, (value) => { if (version === repositoryVersion) renderSnapshots(value, selected); });
    }, "primary");
    button(repoActions, "Check repository integrity", (control) => {
      const args = repository();
      void request(control, "check", args, (value) => evidence(`Repository check: ${args.repo}`, value));
    });
    const backupCard = section("Back up a source", "The OS validates repository and source permissions. No schedule or background backup is created.");
    const source = field(backupCard, "Source path", { placeholder: "/home/user/Documents", autocomplete: "off" });
    const tag = field(backupCard, "Optional backup tag", { placeholder: "documents", maxlength: "128" });
    button(backupCard, "Review backup...", () => {
      const args = { ...repository(), source: absolute(source.value.trim(), "Source") };
      if (tag.value.trim()) {
        if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(tag.value.trim())) throw new Error("Tag must use letters, digits, dot, underscore or hyphen.");
        args.tag = tag.value.trim();
      }
      review("backup", args, "Create backup", "Read the selected source into this repository using its stored credential. This can take time; do not retry an uncertain request.");
    }, "primary");
    const restoreCard = section("Restore selected snapshot", "Choose the destination explicitly. Restoring can write into existing data; a successful request is not a verified recovery exercise.");
    const destination = field(restoreCard, "Restore destination", { placeholder: "/home/user/Restore", autocomplete: "off" });
    button(restoreCard, "Review restore...", () => review("restore", {
      ...repository(), snapshot: snapshot(true), destination: absolute(destination.value.trim(), "Destination"),
    }, "Restore backup", "Review the repository, snapshot and destination carefully. Exact destination backup authority is required."));
    const advanced = ui.node("details", null, { class: "card stack" });
    advanced.append(ui.node("summary", "Repository setup and destructive retention"));
    button(advanced, "Initialize repository...", () => review("init", repository(), "Initialize repository", "Creates a repository at the chosen path. This does not discover or import another App's backups."));
    button(advanced, "Forget selected snapshot...", () => review("forget", {
      ...repository(), snapshot: snapshot(false),
    }, "Forget snapshot", "This removes the exact snapshot from the repository. No undo is promised."), "danger");
    const daily = field(advanced, "Daily snapshots to keep (0-365)", { type: "number", min: "0", max: "365", step: "1", value: "7" });
    const weekly = field(advanced, "Weekly snapshots to keep (0-260)", { type: "number", min: "0", max: "260", step: "1", value: "4" });
    const monthly = field(advanced, "Monthly snapshots to keep (0-120)", { type: "number", min: "0", max: "120", step: "1", value: "12" });
    button(advanced, "Review retention...", () => {
      const args = repository();
      for (const [name, input, max] of [["keep_daily", daily, 365], ["keep_weekly", weekly, 260], ["keep_monthly", monthly, 120]]) {
        const value = Number(input.value);
        if (input.value === "" || !Number.isInteger(value) || value < 0 || value > max) throw new Error(`${name.replaceAll("_", " ")} must be 0-${max}.`);
        args[name] = value;
      }
      review("retention", args, "Apply retention", "Snapshots outside this retention policy may be removed. Zero does not preserve that time bucket. This is not a preview and there is no undo.");
    }, "danger");
    root.append(advanced);
  } else if (app.id === "system-snapshot") {
    const overview = section("Whole-system recovery", "These recovery points are separate from data backups. The OS owns snapshot backends, the index and rollback scheduling.");
    const actions = ui.node("div", null, { class: "toolbar" }); overview.append(actions);
    button(actions, "Inspect recovery backend", (control) => void request(control, "status", {}, (value) => evidence("System recovery status", value)));
    const history = section("System snapshots", "No recovery point is created or activated on page load or selection.");
    history.append(list); ui.replace(list, [ui.node("p", "System snapshots have not been loaded.", { class: "empty" })]);
    const selected = field(history, "Exact system snapshot ID", { placeholder: "snap_<32 lowercase hex digits>", autocomplete: "off" });
    function systemId() {
      if (!/^snap_[0-9a-f]{32}$/.test(selected.value.trim())) throw new Error("System snapshot IDs use snap_ followed by 32 lowercase hexadecimal digits.");
      return selected.value.trim();
    }
    button(actions, "Load recovery points", (control) => void request(control, "list", {}, (value) => renderSnapshots(value, selected)), "primary");
    const create = section("Create a recovery point", "A recovery point is machine-wide and needs system snapshot authority.");
    const description = field(create, "Description (optional)", { placeholder: "Before a planned system change" });
    button(create, "Review creation...", () => review("create", description.value.trim() ? { description: description.value.trim() } : {}, "Create system snapshot", "Create a whole-system recovery point using the available OS backend."), "primary");
    const recovery = section("Selected recovery point", "Rollback is not an immediate verified restore and may be scheduled by the OS. Save work and inspect returned scheduling evidence.");
    button(recovery, "Review rollback...", () => review("rollback", { id: systemId() }, "Request system rollback", "This can replace machine-wide state. Read the OS response for scheduling and any further required steps."), "danger");
    button(recovery, "Delete recovery point...", () => review("delete", { id: systemId() }, "Delete system snapshot", "This permanently removes the selected recovery point. It is not a rollback operation."), "danger");
  } else {
    root.append(ui.node("p", "This identity has no supported backup or system-recovery interface.", { class: "empty" }));
  }
}).catch((error) => {
  document.getElementById("notice").textContent = `Recovery UI unavailable: ${error.message}`;
});
