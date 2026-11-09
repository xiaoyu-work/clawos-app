ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  ui.showApp(app);
  const path = document.querySelector("#path");
  const notice = document.querySelector("#notice");
  const listTool = ClawApp.tool(app, app.id === "fs" ? "ls" : "list");
  let selection = null;
  let generation = 0;
  let editorGeneration = 0;
  let editingPath = null;
  const editor = document.querySelector("#editor");
  const directory = (item) => item.is_dir || ["directory", "dir"].includes(item.type || item.kind);
  const itemPath = (item) => item.path || `${path.value.replace(/\/$/, "")}/${item.name}`;
  const defaults = () => ({ path: selection ? itemPath(selection) : path.value,
    root: path.value, src: selection && itemPath(selection) });
  const fields = {
    path: { label: "Absolute path", type: "text" },
    src: { label: "Source", type: "text", readOnly: true },
    dst: { label: "Destination", type: "text", placeholder: "/home/user/Documents/new-name" },
    content: { label: "Text content", type: "textarea", rows: 10, allowEmpty: true },
    plan: { label: "Plan ID", hidden: true },
    review: { label: "Reviewed fingerprint", readOnly: true },
    confirm: { label: "I confirm the exact changes shown in the review." },
    ttl_seconds: { label: "Review lifetime (seconds)", min: 60, max: 86400 },
  };
  function report(value) {
    const target = document.querySelector("#result");
    if (typeof value === "string") {
      ui.replace(target, [ui.node("p", value, { class: "prose" })]);
      return;
    }
    const entries = ui.node("dl", null, { class: "detail-grid" });
    for (const [label, text] of Object.entries(value || {})) {
      entries.append(ui.node("dt", label.replace(/_/g, " ")),
        ui.node("dd", Array.isArray(text) ? text.join("; ") : text && typeof text === "object" ?
          Object.entries(text).map(([key, value]) => `${key}: ${value}`).join("; ") : text));
    }
    ui.replace(target, [entries]);
  }
  function clearEditor() {
    ++editorGeneration;
    editingPath = null;
    document.querySelector("#text-file").hidden = true;
    document.querySelector("#plan").hidden = true;
  }
  function showPlan(plan) {
    document.querySelector("#plan").hidden = false;
    document.querySelector("#plan-state").textContent =
      `${plan.path} - ${plan.state} - ${plan.before_bytes} to ${plan.after_bytes} bytes - expires ${new Date(plan.expires_at).toLocaleString()}`;
    document.querySelector("#diff").textContent = plan.diff || "No text differences.";
    ui.replace(document.querySelector("#plan-warnings"), (plan.warnings || [])
      .map((warning) => ui.node("p", warning, { class: "small muted" })));
    const actions = document.querySelector("#plan-actions");
    actions.replaceChildren();
    const refresh = ui.node("button", "Refresh review");
    refresh.onclick = () => {
      void ui.run(refresh, () => ClawApp.call("plan_show", { path: plan.path, plan: plan.plan_id }), showPlan, notice);
    };
    actions.append(refresh);
    if (ClawApp.tool(app, "plan_apply")) {
      const apply = ui.node("button", "Apply reviewed changes", { class: "primary" });
      apply.disabled = plan.state !== "draft" || !plan.would_change || plan.diff_truncated ||
        new Date(plan.expires_at).getTime() <= Date.now();
      apply.onclick = () => ui.command(app, "plan_apply", {
        path: plan.path, plan: plan.plan_id, review: plan.review,
      }, async (result) => {
        showPlan(result);
        editor.readOnly = true;
        document.querySelector("#prepare").disabled = true;
        document.querySelector("#edit-state").textContent =
          "Apply reported by App. Reload the file before preparing another edit.";
        await load();
      }, { title: "Apply reviewed changes?", submitLabel: "Confirm and apply",
        description: "Apply this exact reviewed plan. Changed, expired or already consumed plans are refused.",
        fields: { ...fields, path: { label: "Target path", readOnly: true } } });
      actions.append(apply);
    }
  }
  function openText(item) {
    const request = ++editorGeneration;
    const filename = itemPath(item);
    return ui.run(null, () => ClawApp.call("read", { path: filename, limit: 65536 }), (result) => {
      if (request !== editorGeneration) return;
      if (typeof result.content !== "string") throw new Error("The App returned no text to preview.");
      editingPath = result.path || filename;
      editor.value = result.content;
      editor.readOnly = !!result.truncated || !ClawApp.tool(app, "plan_write");
      document.querySelector("#file-title").textContent = editingPath;
      document.querySelector("#edit-state").textContent = result.truncated ?
        "This file exceeds the 64 KiB review limit. The partial preview cannot overwrite the file." : "Loaded. Edits are not saved until reviewed and applied.";
      document.querySelector("#prepare").disabled = editor.readOnly;
      document.querySelector("#text-file").hidden = false;
      document.querySelector("#plan").hidden = true;
    }, notice);
  }
  function select(item) {
    selection = item;
    clearEditor();
    const description = ui.node("dl", null, { class: "detail-grid" });
    for (const [label, value] of [["Path", itemPath(item)], ["Type", directory(item) ? "Directory" : item.type || item.mime || "File"],
      ["Size", item.size === undefined ? "Not loaded" : `${item.size} bytes`], ["Modified", item.modified || item.mtime || "Not loaded"]]) {
      description.append(ui.node("dt", label), ui.node("dd", value));
    }
    ui.replace(document.querySelector("#selection"), [description]);
    const actions = document.querySelector("#file-actions");
    actions.replaceChildren();
    if (directory(item) && listTool) {
      const open = ui.node("button", "Open folder");
      open.onclick = () => { path.value = itemPath(item); void load(); };
      actions.append(open);
    }
    for (const [command, label] of [["read", "Open text"], ["stat", "Properties"], ["metadata", "Properties"],
      ["reveal", "Show on desktop"], ["summarize", "Summarize"], ["explain", "Explain"],
      ["find_similar", "Similar files"], ["plan_show", "Existing review"]]) {
      if (!ClawApp.tool(app, command) || command === "read" && directory(item)) continue;
      const button = ui.node("button", label);
      button.onclick = () => {
        if (command === "read") { void openText(item); return; }
        void ui.run(button, () => ClawApp.call(command, { path: itemPath(item) }),
          command === "plan_show" ? showPlan : command === "find_similar" ? display : report, notice);
      };
      actions.append(button);
    }
    for (const [command, label] of [["rename", "Rename"], ["move", "Move"], ["copy", "Copy"]]) {
      if (!ClawApp.tool(app, command)) continue;
      const button = ui.node("button", label);
      button.onclick = () => ui.command(app, command, { src: itemPath(item) }, async (result) => {
        report(result); await load();
      }, { title: `${label} ${item.name || itemPath(item)}`, submitLabel: label, fields });
      actions.append(button);
    }
    if (ClawApp.tool(app, "rm")) {
      const remove = ui.node("button", "Delete", { class: "danger" });
      remove.onclick = () => ui.command(app, "rm", { path: itemPath(item) }, async (result) => {
        report(result); await load();
      }, { title: "Delete this item?", submitLabel: "Delete", fields: {
        ...fields, path: { label: "Delete path", readOnly: true },
      }, description: directory(item) ? "This removes the directory and all of its contents. Recovery is not guaranteed." :
        "This removes the file. Recovery is not guaranteed." });
      actions.append(remove);
    }
    if (ClawApp.tool(app, "tag") && !directory(item)) {
      const tag = ui.node("button", "Add tags");
      tag.onclick = () => ui.command(app, "tag", { path: itemPath(item) }, report,
        { title: "Add file tags", submitLabel: "Add tags", fields: {
          ...fields, path: { label: "File", readOnly: true },
          tags: { label: "Tags", type: "text", placeholder: "work, project",
            format: (values) => values.join(", "),
            parse: (value) => value.split(",").map((item) => item.trim()).filter(Boolean) },
        } });
      actions.append(tag);
    }
  }
  function display(value) {
    const values = ui.rows(value, ["entries", "files", "matches", "items", "results", "similar"]);
    if (listTool && value && value.path) path.value = value.path;
    document.querySelector("#list-state").textContent = `${values.length} items${value && value.hint ? ` - ${value.hint}` : ""}`;
    values.sort((a, b) => Number(directory(b)) - Number(directory(a)) ||
      String(a.name || a.path).localeCompare(String(b.name || b.path)));
    ui.table(document.querySelector("#files"), values, [
      { label: "Name", value: (item) => item.name || item.path },
      { label: "Type", value: (item) => item.type || item.kind || (item.is_dir ? "Directory" : "File") },
      { label: "Bytes", key: "size" }, { label: "Details", value: (item) => item.snippet || item.modified || item.mtime },
    ], { label: "Select", run: select });
  }
  function load() {
    selection = null;
    document.querySelector("#file-actions").replaceChildren();
    const request = ++generation;
    if (!listTool || !path.value) return;
    return ui.run(document.querySelector("#open"), () => ClawApp.call(listTool.name, { path: path.value }),
      (result) => { if (request === generation) display(result); }, notice);
  }
  document.querySelector("#open").disabled = !listTool;
  document.querySelector("#open").onclick = () => { clearEditor(); void load(); };
  document.querySelector("#path").onkeydown = (event) => {
    if (event.key === "Enter") { event.preventDefault(); clearEditor(); void load(); }
  };
  document.querySelector("#parent").disabled = !listTool;
  document.querySelector("#parent").onclick = () => {
    const parent = path.value.replace(/\/+$/, "").slice(0, path.value.replace(/\/+$/, "").lastIndexOf("/")) || "/";
    path.value = parent;
    clearEditor();
    void load();
  };
  document.querySelector("#search").disabled = !ClawApp.tool(app, "search");
  document.querySelector("#search").onclick = () => {
    if (ClawApp.tool(app, "search")) ui.command(app, "search", {
      path: path.value, root: path.value, query: document.querySelector("#query").value,
    }, display, { title: app.id === "docs" ? "Search indexed documents" : "Search files",
      submitLabel: "Search", fields: { query: { label: "Search query", type: "text" },
        path: fields.path, root: { label: "Search directory", type: "text" } } });
  };
  editor.oninput = () => {
    ++editorGeneration;
    document.querySelector("#edit-state").textContent = "Unsaved edits. Review the exact proposed diff before applying.";
    document.querySelector("#plan").hidden = true;
  };
  document.querySelector("#prepare").onclick = (event) => {
    if (!editingPath || editor.readOnly) return;
    const request = editorGeneration;
    void ui.run(event.target, () => ClawApp.call("plan_write", { path: editingPath, content: editor.value }),
      (result) => { if (request === editorGeneration) showPlan(result); }, notice);
  };
  const actions = document.querySelector("#actions");
  for (const [command, label] of [["mkdir", "New folder"], ["plan_write", "New text file"],
    ["recent", "Recent files"], ["index", "Index documents"], ["status", "Index status"], ["configure", "Configure index"]]) {
    if (!ClawApp.tool(app, command)) continue;
    const button = ui.node("button", label);
    button.onclick = () => {
      if (["mkdir", "plan_write"].includes(command)) {
        ui.command(app, command, { path: path.value.replace(/\/$/, "") + "/" }, command === "plan_write" ?
          showPlan : async (result) => { report(result); await load(); },
        { title: label, submitLabel: command === "plan_write" ? "Prepare review" : "Create folder", fields });
      } else {
        void ui.run(button, () => ClawApp.call(command),
          command === "recent" ? display : report, notice);
      }
    };
    actions.append(button);
  }
  ui.allTools(document.querySelector("#more"), app, (value) => ui.output(document.querySelector("#result"), value), defaults);
  if (app.id === "docs") {
    path.hidden = true;
    document.querySelector("#parent").hidden = true;
    document.querySelector("#open").hidden = true;
    document.querySelector("#query").placeholder = "Search your document index";
    notice.textContent = "Document search uses this App's authorized Recoll index, not another App's filesystem service.";
  } else notice.textContent = "Choose an absolute directory path. The OS authorizes only the requested resources.";
});
