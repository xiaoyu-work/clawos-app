ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  ui.showApp(app);
  const accounts = document.querySelector("#accounts");
  const folders = document.querySelector("#folders");
  const notice = document.querySelector("#notice");
  let selected = null;
  const defaults = () => ({ account: accounts.value, folder: folders.value,
    id: selected && selected.id, "request-id": crypto.randomUUID() });
  function list(result) {
    const messages = ui.rows(result);
    ui.replace(document.querySelector("#messages"), messages.length ? messages.map((item) => {
      const button = ui.node("button");
      button.append(ui.node("strong", item.subject || item.title || "(No subject)"),
        ui.node("p", item.sender || item.from || "", { class: "small muted" }));
      button.onclick = () => {
        selected = item;
        void ui.run(button, () => ClawApp.call("read", { account: accounts.value, id: item.id }), (value) => {
          document.querySelector("#subject").textContent = value.subject || item.subject || "Message";
          document.querySelector("#sender").textContent = value.sender || value.from || "";
          document.querySelector("#message").textContent = value.body || value.text || JSON.stringify(value, null, 2);
          const actions = document.querySelector("#message-actions"); actions.replaceChildren();
          ui.actions(actions, app, [{ command: "draft_save", label: "Save reply draft" },
            { command: "attachment_download", label: "Download attachment" }, { command: "draft_send", label: "Review draft delivery" }],
          (response) => ui.output(document.querySelector("#ai-result"), response), defaults);
        }, notice);
      };
      return button;
    }) : [ui.node("p", "No messages returned.", { class: "empty" })]);
  }
  function load() {
    if (!ClawApp.tool(app, "list")) return;
    return ui.run(document.querySelector("#refresh"), () => ClawApp.call("list", {
      account: accounts.value, folder: folders.value,
    }), list, notice);
  }
  accounts.onchange = () => {
    if (ClawApp.tool(app, "folders")) void ui.run(null, () => ClawApp.call("folders", { account: accounts.value }), (result) => {
      const values = ui.rows(result, ["folders", "items"]);
      if (values.length) ui.replace(folders, values.map((item) => ui.node("option",
        typeof item === "string" ? item : item.name || item.id, { value: typeof item === "string" ? item : item.id || item.name })));
      void load();
    }, notice);
  };
  folders.onchange = load;
  document.querySelector("#refresh").onclick = load;
  document.querySelector("#search").onclick = (event) => {
    if (ClawApp.tool(app, "search")) void ui.run(event.target, () => ClawApp.call("search", {
      account: accounts.value, folder: folders.value, query: document.querySelector("#query").value,
    }), list, notice);
  };
  const compose = ClawApp.tool(app, "draft_save") || ClawApp.tool(app, "send");
  document.querySelector("#compose").disabled = !compose;
  document.querySelector("#compose").onclick = () => ui.command(app, compose.name, defaults(),
    (value) => ui.output(document.querySelector("#ai-result"), value));
  ui.actions(document.querySelector("#ai-actions"), app, ["summarize", "smart_reply", "smart_compose", "translate", "triage", "chat", "draft"],
    (value) => ui.output(document.querySelector("#ai-result"), value));
  ui.allTools(document.querySelector("#more"), app, (value) => ui.output(document.querySelector("#ai-result"), value), defaults);
  if (ClawApp.tool(app, "accounts")) void ui.run(null, () => ClawApp.call("accounts"), (result) => {
    const values = ui.rows(result, ["accounts", "items"]);
    ui.replace(accounts, values.map((item) => ui.node("option", item.name || item.label || item.id, { value: item.id || item.account })));
    accounts.onchange();
  }, notice);
  else {
    accounts.hidden = true; folders.hidden = true; document.querySelector("#messages").hidden = true;
    document.querySelector("#search").disabled = true; document.querySelector("#refresh").disabled = true;
    notice.textContent = app.id === "mail-ai" ? "Choose an explicit Mail AI operation below." : "This delivery entry uses its configured OS credentials.";
  }
});
