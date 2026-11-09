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
    return;
  }
  if (app.id !== "clipboard-manager") {
    $("selection-workspace").hidden = true;
    $("notice").textContent = "This identity has no supported clipboard interface.";
    return;
  }
  $("selection-workspace").hidden = false;

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
