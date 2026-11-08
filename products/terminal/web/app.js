ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  ui.showApp(app);
  const form = document.querySelector("#command");
  const notice = document.querySelector("#notice");
  form.onsubmit = (event) => {
    event.preventDefault();
    let arguments_;
    try { arguments_ = form.elements.arguments.value ? JSON.parse(form.elements.arguments.value) : []; }
    catch { notice.textContent = "Arguments must be a JSON array of strings."; return; }
    if (!Array.isArray(arguments_) || arguments_.some((item) => typeof item !== "string")) {
      notice.textContent = "Arguments must be a JSON array of strings."; return;
    }
    void ui.run(form.querySelector("button"), () => ClawApp.call("run", {
      command: form.elements.command.value, arguments: arguments_,
    }), (value) => {
      document.querySelector("#output").textContent = typeof value === "string" ? value :
        [value.stdout, value.stderr].filter((item) => typeof item === "string").join("\n") || JSON.stringify(value, null, 2);
    }, notice);
  };
  ui.actions(document.querySelector("#actions"), app, [{ command: "script", label: "Run script" },
    { command: "start", label: "Start process" }, { command: "ps", label: "Processes" },
    { command: "stop", label: "Stop process" }, { command: "which", label: "Find executable" }],
  (value) => ui.output(document.querySelector("#processes"), value));
  ui.allTools(document.querySelector("#more"), app, (value) => ui.output(document.querySelector("#processes"), value));
});
