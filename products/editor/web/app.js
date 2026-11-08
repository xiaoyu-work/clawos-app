ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  ui.showApp(app);
  const path = document.querySelector("#path");
  const editor = document.querySelector("#editor");
  const notice = document.querySelector("#notice");
  editor.oninput = () => { document.querySelector("#state").textContent = "Unsaved edits"; };
  document.querySelector("#open").onclick = (event) => void ui.run(event.target,
    () => ClawApp.call("read", { path: path.value }), (value) => {
      const content = typeof value === "string" ? value : value.content;
      if (typeof content !== "string") throw new Error("The App returned no editable text.");
      editor.value = content; document.querySelector("#state").textContent = "Loaded";
    }, notice);
  document.querySelector("#save").onclick = (event) => void ui.run(event.target,
    () => ClawApp.call("write", { path: path.value, content: editor.value }), (value) => {
      ui.output(document.querySelector("#result"), value);
      document.querySelector("#state").textContent = "Save reported by App";
    }, notice);
  const defaults = () => ({ path: path.value });
  ui.actions(document.querySelector("#actions"), app, [{ command: "replace_range", label: "Find and replace" },
    { command: "summarize", label: "Summarize" }, { command: "explain", label: "Explain" }, { command: "rewrite", label: "Rewrite" }],
  (value) => ui.output(document.querySelector("#result"), value), defaults);
  ui.allTools(document.querySelector("#more"), app, (value) => ui.output(document.querySelector("#result"), value), defaults);
});
