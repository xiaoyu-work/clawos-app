ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const $ = (selector) => document.querySelector(selector);
  const has = (command) => Boolean(ClawApp.tool(app, command));
  const native = app.id === "cosmic-term";
  let busy = false;
  let jobs = [];
  let jobsGeneration = 0;
  const history = [];
  ui.showApp(app);

  function call(command, args = {}) {
    const tool = ClawApp.tool(app, command);
    if (!tool) throw new Error(`This entry does not declare ${command}.`);
    return ClawApp.call(tool.name, args);
  }
  function update() {
    const background = $("#mode").value === "start";
    $("#run").textContent = background ? "Start background job" : $("#shell").checked ? "Execute shell command" : "Run program";
    $("#timeout").disabled = busy || background;
    $("#shell").disabled = busy || background;
    $("#refresh-jobs").disabled = busy || !has("ps");
    $("#which").disabled = busy || !has("which");
    $("#run").disabled = busy || !has(background ? "start" : "run");
    $("#code").required = $("#script-source").value === "inline";
    $("#script-file").required = $("#script-source").value === "file";
    $("#code-label").hidden = $("#script-source").value !== "inline";
    $("#script-file-label").hidden = $("#script-source").value !== "file";
  }
  async function perform(action, render, failed) {
    if (busy) return;
    busy = true;
    const controls = Array.from(document.querySelectorAll("button, input, select, textarea")).filter((control) => !control.disabled);
    controls.forEach((control) => { control.disabled = true; });
    const result = await ui.run(null, async () => {
      const value = await action();
      ui.output($("#raw"), value);
      if (value && value.error && !value.timed_out) throw new Error(String(value.error));
      return value;
    }, render, $("#notice"));
    if (result === undefined && failed) failed();
    busy = false;
    controls.forEach((control) => { control.disabled = false; });
    update();
  }
  function addArgument(value = "") {
    const row = ui.node("div", null, { class: "row" });
    const input = ui.node("input", null, { "aria-label": "Program argument", autocomplete: "off" });
    input.value = value;
    const remove = ui.node("button", "Remove", { type: "button" });
    remove.onclick = () => { if (!busy) row.remove(); };
    row.append(input, remove);
    $("#arguments").append(row);
  }
  function argumentsList() {
    return Array.from($("#arguments").querySelectorAll("input")).map((input) => input.value);
  }
  function clearOutput(label) {
    $("#exit").textContent = "Pending - no confirmed result";
    $("#stdout").textContent = "";
    $("#stderr").textContent = "";
    $("#output-info").textContent = label;
    $("#outcome").textContent = "Request sent only once. If it fails or times out, inspect state before retrying.";
  }
  function renderOutput(value) {
    if (!value || typeof value.stdout !== "string" || typeof value.stderr !== "string") {
      throw new Error("The backend returned no captured output. The execution outcome is not confirmed.");
    }
    $("#stdout").textContent = value.stdout || "(empty)";
    $("#stderr").textContent = value.stderr || "(empty)";
    $("#exit").textContent = value.timed_out ? `Timed out${value.exit_code == null ? "" : ` - exit ${value.exit_code}`}` :
      value.exit_code == null ? "Exit status unknown" : `Exit ${value.exit_code}`;
    $("#output-info").textContent = [
      value.timed_out ? "The timeout was reported by the backend." : "Output is a completed bounded capture, not a live terminal.",
      value.truncated ? "The backend truncated output." : "",
    ].filter(Boolean).join(" ");
    $("#outcome").textContent = value.timed_out ? "Backend reported a timeout. No automatic retry." :
      value.exit_code === 0 ? "Program exited with code 0." : `Program returned ${value.exit_code ?? "an unknown exit status"}; this is not reported as success.`;
  }
  function remember(request, value) {
    history.unshift({ ...request, exit: value.exit_code, pid: value.pid });
    history.splice(20);
    ui.replace($("#history"), history.map((entry) => {
      const button = ui.node("button", `${entry.command} ${entry.arguments.map((arg) => JSON.stringify(arg)).join(" ")} - ${
        entry.pid ? `started PID ${entry.pid}` : `exit ${entry.exit ?? "unknown"}`}`, { type: "button" });
      button.onclick = () => {
        if (busy) return;
        $("#program").value = entry.command;
        $("#arguments").replaceChildren();
        entry.arguments.forEach(addArgument);
        $("#mode").value = entry.mode;
        $("#shell").checked = entry.shell === true;
        $("#outcome").textContent = "Request copied to the form. Review and submit to execute.";
        update();
      };
      return button;
    }));
  }
  function renderJobs(value) {
    if (!value || !Array.isArray(value.processes)) throw new Error("The backend returned no process registry.");
    jobs = value.processes;
    jobsGeneration++;
    ui.replace($("#jobs"), jobs.map((job) => {
      const card = ui.node("article", null, { class: "card stack" });
      card.append(ui.node("h3", `PID ${job.pid}`), ui.node("p",
        Array.isArray(job.command) ? job.command.map((arg) => JSON.stringify(arg)).join(" ") : "Command not reported", { class: "code" }),
      ui.node("p", `Started: ${job.started || "not reported"}`, { class: "muted small" }));
      if (has("stop") && Number.isInteger(job.pid) && job.pid > 0) {
        const button = ui.node("button", "Review stop request", { type: "button", class: "danger" });
        const version = jobsGeneration;
        button.onclick = () => stopDialog(job, version);
        card.append(button);
      }
      return card;
    }));
    if (!jobs.length) ui.replace($("#jobs"), [ui.node("p", "No live jobs in this entry's background registry.", { class: "empty" })]);
  }
  function stopDialog(job, version) {
    if (busy || version !== jobsGeneration || !jobs.includes(job)) return;
    const dialog = ui.node("dialog");
    dialog.append(ui.node("h2", `Stop registered PID ${job.pid}?`), ui.node("p",
      "Sends SIGTERM to this exact PID. Registry presence is not a process-identity token; the process may exit or the PID may be reused. No arbitrary PID field or automatic retry is provided."));
    const form = ui.node("form");
    const label = ui.node("label", "I reviewed the selected registered process and want to send this signal.");
    const confirm = ui.node("input", null, { type: "checkbox", required: "" });
    label.append(confirm);
    const actions = ui.node("div", null, { class: "toolbar" });
    const cancel = ui.node("button", "Cancel", { type: "button" });
    const submit = ui.node("button", `Signal PID ${job.pid}`, { type: "submit", class: "danger" });
    cancel.onclick = () => dialog.close();
    actions.append(cancel, submit);
    form.append(label, actions);
    form.onsubmit = (event) => {
      event.preventDefault();
      if (busy || !form.reportValidity() || version !== jobsGeneration || !jobs.includes(job)) return;
      jobs = [];
      jobsGeneration++;
      ui.replace($("#jobs"), [ui.node("p", "Refresh jobs to obtain a new registry snapshot before another control.", { class: "empty" })]);
      $("#outcome").textContent = `Stop requested once for PID ${job.pid}. Its outcome is not yet confirmed.`;
      void perform(() => call("stop", { pid: job.pid }), (value) => {
        $("#outcome").textContent = value.pid === job.pid && value.status === "stopped" ?
          `Backend reported the stop signal for PID ${job.pid}. This does not independently verify process exit.` :
          "The stop outcome was not confirmed. Refresh the registry before another request.";
      }, () => {
        $("#outcome").textContent = `Stop of PID ${job.pid} failed or is unconfirmed. Refresh the registry; no signal is retried automatically.`;
      }).finally(() => dialog.close());
    };
    dialog.append(form);
    dialog.addEventListener("close", () => dialog.remove());
    document.body.append(dialog);
    dialog.showModal();
  }

  $("#add-argument").onclick = () => { if (!busy) addArgument(); };
  $("#mode").onchange = update;
  $("#shell").onchange = update;
  $("#script-source").onchange = update;
  $("#shell-option").hidden = native || !ClawApp.tool(app, "run")?.args.some((arg) => arg.name === "shell");
  if (has("start")) $("#mode").append(ui.node("option", "Start a registered background job", { value: "start" }));
  const timeoutArg = ClawApp.tool(app, "run")?.args.find((arg) => arg.name === (native ? "timeout_secs" : "timeout"));
  $("#timeout").value = String(timeoutArg?.default ?? 30);
  if (native) $("#timeout").max = "600";
  $("#command").onsubmit = (event) => {
    event.preventDefault();
    if (busy || !$("#command").reportValidity()) return;
    const mode = $("#mode").value;
    const command = $("#program").value;
    const arguments_ = argumentsList();
    const args = { command, arguments: arguments_ };
    const shell = mode === "run" && !native && $("#shell").checked;
    if (mode === "run") {
      args[native ? "timeout_secs" : "timeout"] = Number($("#timeout").value);
      if (!native) args.shell = shell;
    }
    clearOutput(`${mode === "start" ? "Background request" : "Captured execution"}: ${command}`);
    void perform(() => call(mode, args), (value) => {
      if (mode === "start") {
        if (!Number.isInteger(value.pid) || value.pid < 1) throw new Error("No background PID was confirmed. Refresh jobs before considering another start.");
        $("#exit").textContent = `Started PID ${value.pid}`;
        $("#stdout").textContent = "Background output is not exposed by this entry's tools.";
        $("#stderr").textContent = "No live background stream is available.";
        $("#outcome").textContent = `Backend reported PID ${value.pid}. Refresh jobs to observe its registry state.`;
      } else renderOutput(value);
      remember({ command, arguments: arguments_, mode, shell }, value);
    }, () => {
      $("#exit").textContent = "Failed or unconfirmed outcome";
      $("#outcome").textContent = "No completed execution result confirmed. Inspect state before another execution; nothing is retried automatically.";
    });
  };
  $("#which").onclick = () => {
    const program = $("#program").value;
    if (!program.trim()) { $("#lookup").textContent = "Enter an executable name first."; return; }
    $("#lookup").textContent = "";
    void perform(() => call("which", native ? { program } : { name: program }), (value) => {
      $("#lookup").textContent = value.path ? `${program}: ${value.path}` : `${program}: no executable found.`;
    });
  };
  $("#scripts").hidden = !has("script");
  $("#script-form").onsubmit = (event) => {
    event.preventDefault();
    if (busy || !$("#script-form").reportValidity()) return;
    const inline = $("#script-source").value === "inline";
    const args = { lang: $("#language").value, timeout: Number($("#script-timeout").value) };
    if (inline) args.code = [$("#code").value];
    else args.file = $("#script-file").value;
    clearOutput(`Explicit ${args.lang} script request`);
    void perform(() => call("script", args), renderOutput, () => {
      $("#exit").textContent = "Failed or unconfirmed script outcome";
      $("#outcome").textContent = "Script result not confirmed. No automatic retry.";
    });
  };
  $("#refresh-jobs").onclick = () => {
    jobs = [];
    jobsGeneration++;
    ui.replace($("#jobs"), [ui.node("p", "Loading registry...", { class: "empty" })]);
    void perform(() => call("ps"), renderJobs, () => {
      $("#jobs").replaceChildren(ui.node("p", "Process registry unavailable. No empty registry is inferred and no job can be selected.", { class: "empty" }));
    });
  };
  $("#jobs-help").textContent = has("ps") ?
    "Only this exec entry's registry is shown, not native PTYs or all host processes. Refresh is explicit; background output files are not readable through these tools." :
    "This native entry has no background registry, job-list or signal tool. Its bounded command runner is separate from native PTYs.";
  $("#jobs").append(ui.node("p", has("ps") ? "Refresh to inspect registered jobs." : "Job controls are unavailable for this entry.", { class: "empty" }));
  $("#history").append(ui.node("p", "No requests completed in this page.", { class: "empty" }));
  $("#desktop").hidden = !has("open");
  $("#desktop").onclick = () => ui.command(app, "open", {}, (value) => {
    ui.output($("#raw"), value);
    $("#outcome").textContent = value.opened === true ? "Native terminal activation reported. No command was sent to it." : "Native activation was not confirmed.";
  }, { title: "Open a native terminal window", submitLabel: "Open native window",
    description: "Explicit desktop activation through this entry's fixed OS service, not an embedded PTY. No command is automatically executed.",
    fields: { cwd: { label: "Optional authorized absolute working directory", type: "text" } } });
  update();
});
