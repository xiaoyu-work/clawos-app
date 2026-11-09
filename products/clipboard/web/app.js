ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const $ = (id) => document.getElementById(id);
  let busy = false;
  let reviewing = false;
  let selectionVersion = 0;
  ui.showApp(app);
  if (app.id === "panel-clipboard") {
    $("selection-workspace").hidden = true;
    $("native-history").hidden = false;
    $("title").textContent = "Clipboard History";
    historyWorkspace();
    return;
  }
  if (app.id !== "clipboard-manager") {
    $("selection-workspace").hidden = true;
    $("notice").textContent = "This identity has no supported clipboard interface.";
    return;
  }
  $("selection-workspace").hidden = false;

  function historyWorkspace() {
    let entries = [];
    let selected = null;
    let loading = false;
    function select(entry) {
      selected = entry;
      $("history-preview").textContent = entry ? entry.preview : "No history item selected.";
      $("history-time").textContent = entry && entry.copied_at ? `CopyQ copy time: ${entry.copied_at}` : "Copy time not reported.";
      $("history-identity").textContent = entry ? entry.identity : "";
      $("history-restore").disabled = loading || !entry;
      $("history-remove").disabled = loading || !entry;
      for (const control of $("history-items").querySelectorAll("button")) {
        control.setAttribute("aria-pressed", String(control.dataset.identity === (entry && entry.identity)));
      }
    }
    function hide(message = "History previews are hidden locally. Load history explicitly to view it again.") {
      entries = [];
      ui.replace($("history-items"), [ui.node("p", message, { class: "muted" })]);
      select(null);
    }
    function show(value) {
      if (!value || !Array.isArray(value.entries) || value.entries.length > 20 ||
          value.entries.some((entry) => !entry || typeof entry.identity !== "string" ||
            !/^[A-Za-z0-9+/]{43}=$/.test(entry.identity) || typeof entry.preview !== "string" ||
            Array.from(entry.preview).length > 181 || entry.preview.includes("\0") ||
            entry.copied_at !== null && typeof entry.copied_at !== "string")) {
        hide("The service returned an invalid history response. No entries are displayed.");
        throw new Error("Invalid OS clipboard history result.");
      }
      entries = value.entries;
      select(null);
      const controls = entries.map((entry, index) => {
        const control = ui.node("button", `${index + 1}. ${entry.preview || "(Whitespace-only text)"}`, {
          type: "button", "aria-pressed": "false",
        });
        control.dataset.identity = entry.identity;
        control.onclick = () => select(entry);
        return control;
      });
      ui.replace($("history-items"), controls.length ? controls : [
        ui.node("p", "CopyQ returned no eligible text history items.", { class: "muted" }),
      ]);
      $("history-state").textContent = `${entries.length} text previews returned (up to 20). This snapshot can become stale.`;
    }
    async function load(control) {
      if (loading) return;
      loading = true;
      hide("Loading existing text history...");
      $("history-hide").disabled = true;
      $("history-clear").disabled = true;
      try {
        const value = await ui.run(control, () => {
          const tool = ClawApp.tool(app, "history.list");
          if (!tool) throw new Error("This identity does not declare history.list.");
          return ClawApp.call(tool.name, {});
        }, show, $("notice"));
        if (value === undefined) {
          hide("History could not be loaded. The service error is shown above.");
          $("history-state").textContent = "History unavailable or invalid; no empty result was substituted.";
        }
      } finally {
        loading = false;
        $("history-hide").disabled = false;
        $("history-clear").disabled = false;
        select(selected);
      }
    }
    function review(command) {
      if (loading || command !== "history.clear" && !selected) return;
      const identity = selected && selected.identity;
      try {
        ui.command(app, command, command === "history.clear" ? {} : { identity }, (value) => {
          hide("History changed or may now be stale. Load it explicitly before another item action.");
          $("history-state").textContent = "Action response received; no automatic retry or refresh.";
          ui.output($("history-result"), value);
          $("notice").textContent = "Inspect history again before another change. No undo is promised.";
        }, {
          title: command === "history.clear" ? "Clear CopyQ history?" :
            command === "history.restore" ? "Restore selected history item?" : "Delete selected history item?",
          description: command === "history.restore" ?
            "This replaces the live clipboard. The OS separately requires clipboard.write:selection as well as history read/write. It does not read the current selection." :
            command === "history.clear" ?
              "This deletes the configured CopyQ history tab's items, not the live selection. Confirm explicitly; no undo or automatic retry is promised." :
              "This deletes only the selected unchanged history item. If it changed or disappeared, refresh instead of guessing its position.",
          submitLabel: command === "history.clear" ? "Clear history" :
            command === "history.restore" ? "Restore to clipboard" : "Delete history item",
          fields: {
            identity: { label: "Selected item identity", readOnly: true },
            confirm: { label: "I confirm clearing this existing clipboard history." },
          },
        });
      } catch (error) { $("notice").textContent = error.message; }
    }
    $("history-load").onclick = (event) => { void load(event.currentTarget); };
    $("history-hide").onclick = () => { hide(); $("history-state").textContent = "Only local previews were hidden. System history and selection are unchanged."; };
    $("history-restore").onclick = () => review("history.restore");
    $("history-remove").onclick = () => review("history.remove");
    $("history-clear").onclick = () => review("history.clear");
  }

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
  function selection(withMime = false) {
    const args = { primary: $("selection").value === "primary" };
    const mime = $("mime").value.trim();
    if (withMime && mime) {
      if (mime.length > 255 || !mime.includes("/") || mime.startsWith("-") || /[\s\u0000-\u001f]/.test(mime)) throw new Error("Enter a MIME type without whitespace or controls, or leave it blank for the OS default.");
      args.mime = mime;
    }
    return args;
  }
  function selectionName(args) { return args.primary ? "Primary selection" : "Clipboard selection"; }
  function evidence(title, value) {
    $("result-title").textContent = title;
    ui.replace($("result"), [detail(value)]);
  }
  async function request(control, command, args, done, status = $("notice"), guardSelection = true) {
    if (busy) return;
    busy = true;
    const version = selectionVersion;
    try {
      await ui.run(control, () => {
        const tool = ClawApp.tool(app, command);
        if (!tool) throw new Error(`This entry does not declare ${command}.`);
        return ClawApp.call(tool.name, args);
      }, (value) => { if (!guardSelection || version === selectionVersion) done(value); }, status);
    } finally { busy = false; }
  }
  function clearPreview() {
    $("content").textContent = "No selection content is displayed.";
    $("content-label").textContent = "Private content preview";
  }
  function reset() {
    selectionVersion++;
    clearPreview();
    ui.replace($("types"), [ui.node("p", "Formats have not been loaded for this selection.", { class: "muted" })]);
    evidence("Clipboard evidence", "Selection or MIME changed. Read again explicitly; no clipboard access occurred.");
  }
  function review(command, args) {
    if (busy || reviewing) return;
    reviewing = true;
    const dialog = ui.node("dialog"); const form = ui.node("form");
    const check = ui.node("input", null, { type: "checkbox", required: "" });
    const label = ui.node("label", `I confirm ${command === "clear" ? "clearing" : "replacing"} the ${selectionName(args).toLowerCase()}.`); label.append(check);
    const status = ui.node("p", "", { class: "notice", role: "status", "aria-live": "polite" });
    const cancel = ui.node("button", "Cancel", { type: "button" });
    const execute = ui.node("button", command === "clear" ? "Clear selection" : "Write source file", { type: "submit", class: "danger" });
    const actions = ui.node("div", null, { class: "toolbar" }); actions.append(cancel, execute);
    form.append(ui.node("p", command === "clear" ? "This clears only the selected Wayland selection, not CopyQ history. No undo is promised." : "This replaces the selected Wayland selection from the exact authorized source file. It does not import history or use the browser clipboard."),
      detail({ selection: selectionName(args), source: args.source || "Not applicable", mime: args.mime || "OS default (argument omitted)" }), label, status, actions);
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (!check.checked || busy) return;
      cancel.disabled = true;
      await request(execute, command, command === "clear" ? { ...args, confirm: true } : args, (value) => {
        clearPreview();
        evidence(`${command === "clear" ? "Clear" : "Write"} response: ${selectionName(args)}`, value);
        $("notice").textContent = "Response received. Read or inspect the selection explicitly before another change; no automatic retry.";
        dialog.close();
      }, status, false);
      cancel.disabled = false; check.checked = false;
      if (dialog.open) status.append(ui.node("span", " The effect may be unknown. Inspect the selection before retrying."));
    };
    cancel.onclick = () => dialog.close();
    dialog.addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
    dialog.addEventListener("close", () => { reviewing = false; dialog.remove(); });
    dialog.append(ui.node("h2", command === "clear" ? "Clear selection?" : "Review clipboard write"), form);
    document.body.append(dialog); dialog.showModal();
  }
  $("selection").onchange = reset;
  $("mime").oninput = reset;
  $("hide-content").onclick = clearPreview;
  $("read").onclick = (event) => {
    try {
      const args = selection(true);
      void request(event.currentTarget, "read", args, (value) => {
        $("content-label").textContent = `${selectionName(args)} content (explicit read; may now be stale)`;
        if (value && typeof value.text === "string") $("content").textContent = value.text === "" ? "(Empty text returned.)" : value.text;
        else if (typeof value === "string") $("content").textContent = value || "(Empty text returned.)";
        else {
          $("content").textContent = "The service did not return a text field. Binary or unavailable content is not decoded or rendered here.";
          evidence("Read response metadata", value);
        }
      });
    } catch (error) { $("notice").textContent = error.message; }
  };
  $("status").onclick = (event) => {
    const args = selection();
    void request(event.currentTarget, "status", args, (value) => evidence(`${selectionName(args)} status`, value));
  };
  $("load-types").onclick = (event) => {
    const args = selection();
    void request(event.currentTarget, "types", args, (value) => {
      const types = value && Array.isArray(value.types) ? value.types : null;
      if (!types) { evidence("Format response", value); return; }
      const buttons = [];
      for (const mime of types) {
        if (typeof mime !== "string") continue;
        const control = ui.node("button", mime, { type: "button" });
        control.onclick = () => { $("mime").value = mime; clearPreview(); selectionVersion++; };
        buttons.push(control);
      }
      ui.replace($("types"), buttons.length ? buttons : [ui.node("p", "No MIME formats returned for this selection.", { class: "muted" })]);
    });
  };
  $("write-form").onsubmit = (event) => {
    event.preventDefault();
    try {
      const source = $("source").value.trim();
      if (!source.startsWith("/") || source.length > 4096 || /[\u0000-\u001f]/.test(source)) throw new Error("Choose an absolute canonical non-symlink source path on the OS filesystem.");
      review("write", { ...selection(true), source });
    } catch (error) { $("notice").textContent = error.message; }
  };
  $("clear").onclick = () => review("clear", selection());
}).catch((error) => {
  document.getElementById("notice").textContent = `Clipboard UI unavailable: ${error.message}`;
});
