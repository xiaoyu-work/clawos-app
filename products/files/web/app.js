ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  ui.showApp(app);
  const path = document.querySelector("#path");
  const notice = document.querySelector("#notice");
  const listTool = ClawApp.tool(app, app.id === "fs" ? "ls" : "list");
  let selection = null;
  const defaults = () => ({ path: selection ? selection.path || `${path.value}/${selection.name}` : path.value,
    root: path.value, src: selection && (selection.path || `${path.value}/${selection.name}`) });
  function display(value) {
    const values = ui.rows(value, ["entries", "files", "items", "results"]);
    if (!values.length && !Array.isArray(value)) { ui.output(document.querySelector("#files"), value); return; }
    ui.table(document.querySelector("#files"), values, [
      { label: "Name", value: (item) => item.name || item.path },
      { label: "Type", value: (item) => item.type || item.kind || (item.is_dir ? "Directory" : "File") },
      { label: "Bytes", key: "size" }, { label: "Modified", value: (item) => item.modified || item.mtime },
    ], { label: "Select", run: (item) => {
      selection = item;
      ui.output(document.querySelector("#selection"), item);
      document.querySelector("#file-actions").replaceChildren();
      ui.actions(document.querySelector("#file-actions"), app, ["read", "stat", "metadata", "rename", "move", "copy",
        "rm", "plan_write", "plan_show", "plan_apply", "summarize", "explain", "find_similar"],
      (result) => ui.output(document.querySelector("#result"), result), defaults);
      if (item.is_dir || item.type === "directory") { path.value = defaults().path; selection = null; void load(); }
    } });
  }
  function load() {
    selection = null;
    if (!listTool) return;
    return ui.run(document.querySelector("#open"), () => ClawApp.call(listTool.name, { path: path.value }), display, notice);
  }
  document.querySelector("#open").disabled = !listTool;
  document.querySelector("#open").onclick = load;
  document.querySelector("#search").onclick = () => {
    if (ClawApp.tool(app, "search")) ui.command(app, "search", {
      path: path.value, root: path.value, query: document.querySelector("#query").value,
    }, display);
  };
  ui.actions(document.querySelector("#actions"), app, [{ command: "mkdir", label: "New folder" },
    { command: "write", label: "New file" }, { command: "recent", label: "Recent files" },
    { command: "index", label: "Index documents" }, { command: "status", label: "Index status" }], display, defaults);
  ui.allTools(document.querySelector("#more"), app, (value) => ui.output(document.querySelector("#result"), value), defaults);
  if (listTool) void load();
});
