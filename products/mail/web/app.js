ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  ui.showApp(app);
  const accounts = document.querySelector("#accounts");
  const folders = document.querySelector("#folders");
  const notice = document.querySelector("#notice");
  const accountItems = new Map();
  let selected = null;
  let generation = 0;
  let readGeneration = 0;
  let folderItems = [];
  const addresses = (value) => Array.isArray(value) ? value.join(", ") : value || "";
  const defaults = () => ({ account: selected && selected.account || accounts.value,
    folder: folders.value, id: selected && selected.id });
  const fields = {
    account: { label: "Account", hidden: true },
    "source-account": { label: "Draft mailbox account", hidden: true },
    "sender-account": { label: "Sender account", type: "text" },
    id: { label: "Saved draft", hidden: true },
    "request-id": { label: "Submission receipt", hidden: true },
    review: { label: "Reviewed draft fingerprint", readOnly: true },
    to: { label: "To", type: "text", placeholder: "alice@example.com, bob@example.com" },
    cc: { label: "Cc", type: "text" },
    subject: { label: "Subject", type: "text" },
    body: { label: "Message", type: "textarea", rows: 10 },
    confirm: { label: "I have reviewed this draft and confirm it may be sent." },
  };
  function resetMessage() {
    selected = null;
    ++readGeneration;
    document.querySelector("#subject").textContent = "Message";
    document.querySelector("#sender").textContent = "";
    document.querySelector("#message").textContent = "Select a message to read it.";
    document.querySelector("#message-actions").replaceChildren();
    document.querySelector("#attachments").replaceChildren();
  }
  function aiResult(result) {
    const target = document.querySelector("#ai-result");
    if (typeof result === "string") {
      ui.replace(target, [ui.node("p", result, { class: "prose" })]);
      return;
    }
    const items = [];
    for (const [key, value] of Object.entries(result || {})) {
      if (["usage", "budget", "model", "provider"].includes(key)) continue;
      const section = ui.node("section", null, { class: "card stack" });
      section.append(ui.node("h3", key.replace(/[-_]/g, " ")));
      const values = Array.isArray(value) ? value : [value];
      for (const item of values) {
        if (item && typeof item === "object") {
          for (const [label, text] of Object.entries(item)) section.append(ui.node("p",
            `${label.replace(/[-_]/g, " ")}: ${Array.isArray(text) ? text.join("; ") : text}`, { class: "prose" }));
        } else section.append(ui.node("p", item, { class: "prose" }));
      }
      items.push(section);
    }
    if (result && result.model) items.push(ui.node("p", `Model: ${result.model}`, { class: "small muted" }));
    ui.replace(target, items);
  }
  function compose(values, replacing) {
    const command = ClawApp.tool(app, "draft_save") ? "draft_save" : "send";
    const context = { account: accounts.value, "request-id": crypto.randomUUID(), ...values };
    ui.command(app, command, context, async (result) => {
      if (result.draft) await reviewDraft(result.draft);
      else notice.textContent = result.sent ?
        "Submitted to Thunderbird. Delivery is not confirmed." : "Mail operation returned.";
    }, {
      title: replacing ? "Edit saved draft" : "Compose email",
      submitLabel: command === "draft_save" ? "Save draft" : "Send email",
      description: replacing ? "Save the edited plain-text body in Thunderbird. Existing attachments and other recipients are retained; HTML formatting is replaced by plain text. This does not send mail." :
        command === "draft_save" ? "Save in the selected sender's Thunderbird Drafts folder. This does not send mail." :
        "Review the recipients and complete message before sending.",
      fields,
    });
  }
  function showDraft(draft) {
    const message = draft.message;
    const target = document.querySelector("#draft-content");
    const details = ui.node("dl", null, { class: "detail-grid" });
    for (const [label, value] of [["From", message.from], ["To", addresses(message.to)],
      ["Cc", addresses(message.cc)], ["Bcc", addresses(message.bcc)], ["Subject", message.subject],
      ["Mailbox account", message.account]]) details.append(ui.node("dt", label), ui.node("dd", value || "(None)"));
    const content = [details, ui.node("p", message.body || "(Empty message)", { class: "prose" })];
    if (message.html) {
      const html = ui.node("details");
      html.append(ui.node("summary", "Complete HTML source included in this review"),
        ui.node("pre", message.html));
      content.push(html);
    }
    for (const attachment of message.attachments || []) content.push(ui.node("p",
      `${attachment.name} - ${attachment.size} bytes - ${attachment.sha256 || ""}`, { class: "small" }));
    content.push(ui.node("p", `Review: ${draft.review}`, { class: "small muted" }));
    ui.replace(target, content);
    const actions = document.querySelector("#draft-actions");
    actions.replaceChildren();
    const account = message.account;
    if (ClawApp.tool(app, "draft_save")) {
      const edit = ui.node("button", "Edit draft");
      edit.onclick = () => compose({ account: accounts.value, id: draft.id,
        "source-account": account, to: addresses(message.to), cc: addresses(message.cc),
        subject: message.subject, body: message.body }, true);
      actions.append(edit);
    }
    if (ClawApp.tool(app, "draft_send")) {
      const senders = ui.node("select", null, { "aria-label": "Send draft from account" });
      for (const item of accountItems.values()) {
        if (item.can_send && item.id.split(":")[0] === account.split(":")[0]) {
          senders.append(ui.node("option", item.name || item.id, { value: item.id }));
        }
      }
      if (Array.from(senders.options).some((option) => option.value === accounts.value)) senders.value = accounts.value;
      const send = ui.node("button", "Send reviewed draft", { class: "primary" });
      send.disabled = !senders.options.length;
      send.onclick = () => ui.command(app, "draft_send", {
        account, id: draft.id, "sender-account": senders.value, review: draft.review,
        "request-id": crypto.randomUUID(),
      }, (result) => {
        document.querySelector("#draft").hidden = true;
        document.querySelector("#message").textContent = result.sent ?
          "Submitted to Thunderbird. Delivery is not confirmed." : "Draft operation returned.";
        if (result.draft_removed === false) document.querySelector("#message").textContent +=
          " The source draft was retained; do not send it again.";
      }, { title: "Send reviewed draft?", submitLabel: "Confirm and send", fields: {
        ...fields, "sender-account": { label: "Sender account", readOnly: true },
      }, description: "Send the unchanged reviewed content above, including all recipients and attachments. Sending is not delivery proof." });
      actions.append(senders, send);
    }
    document.querySelector("#draft").hidden = false;
  }
  function reviewDraft(draft) {
    if (!ClawApp.tool(app, "native_draft")) return;
    const request = generation;
    return ui.run(null, () => ClawApp.call("native_draft", { id: draft.id }), (result) => {
      if (request === generation) showDraft(result.draft);
    }, notice);
  }
  function displayMessage(value, item) {
    selected = value;
    document.querySelector("#subject").textContent = value.subject || item.subject || "(No subject)";
    document.querySelector("#sender").textContent = `${value.from || ""}${value.date ? ` - ${new Date(value.date).toLocaleString()}` : ""}`;
    document.querySelector("#message").textContent = value.body || "(No plain-text body)";
    document.querySelector("#ai-input").value = value.body || "";
    const attachments = document.querySelector("#attachments");
    attachments.replaceChildren();
    if (value.truncated) attachments.append(ui.node("p", "The displayed message is truncated.", { class: "notice" }));
    for (const item of value.attachments || []) {
      const row = ui.node("div", null, { class: "row" });
      row.append(ui.node("span", `${item.name} - ${item.size} bytes`, { class: "small" }));
      if (ClawApp.tool(app, "attachment_download")) {
        const download = ui.node("button", "Save attachment");
        download.onclick = () => ui.command(app, "attachment_download", {
          ...defaults(), attachment: item.id,
        }, (result) => {
          row.append(ui.node("span", `Saved ${result.bytes} bytes to ${result.path}`, { class: "small muted" }));
          download.disabled = true;
        }, { title: `Save ${item.name}`, submitLabel: "Save attachment", fields: {
          ...fields, attachment: { label: "Attachment", hidden: true },
          output: { label: "Absolute destination path", type: "text", placeholder: "/home/user/Downloads/attachment.pdf" },
        }, description: "Choose an existing destination directory. An existing file is never overwritten." });
        row.append(download);
      }
      attachments.append(row);
    }
    const actions = document.querySelector("#message-actions");
    actions.replaceChildren();
    if (ClawApp.tool(app, "draft_save") || ClawApp.tool(app, "send")) {
      const reply = ui.node("button", "Reply");
      reply.onclick = () => compose({ to: value.from, subject: /^re:/i.test(value.subject || "") ?
        value.subject : `Re: ${value.subject || ""}`, body: `\n\n${value.body || ""}` });
      actions.append(reply);
    }
    const folder = folderItems.find((entry) => entry.id === value.folder);
    if (folder && folder.special_use && folder.special_use.includes("drafts") && ClawApp.tool(app, "native_draft")) {
      const review = ui.node("button", "Review saved draft");
      review.onclick = () => { void reviewDraft(value); };
      actions.append(review);
    }
  }
  function list(result) {
    const messages = ui.rows(result);
    const limit = Number(document.querySelector("#limit").value);
    document.querySelector("#message-count").textContent = `${messages.length} messages${messages.length === limit ?
      " shown; narrow the search to find more." : "."}`;
    ui.replace(document.querySelector("#messages"), messages.length ? messages.map((item) => {
      const button = ui.node("button");
      button.append(ui.node("strong", `${item.unread ? "Unread: " : ""}${item.subject || "(No subject)"}`),
        ui.node("p", item.from || "", { class: "small muted" }),
        ui.node("p", item.date ? new Date(item.date).toLocaleString() : "", { class: "small muted" }));
      button.onclick = () => {
        const request = ++readGeneration;
        void ui.run(button, () => ClawApp.call("read", { account: item.account || accounts.value, id: item.id }), (value) => {
          if (request === readGeneration) displayMessage(value, item);
        }, notice);
      };
      return button;
    }) : [ui.node("p", "No messages returned.", { class: "empty" })]);
  }
  function load(searching) {
    if (!ClawApp.tool(app, "list") || !accounts.value) return;
    const request = ++generation;
    resetMessage();
    const arguments_ = { account: accounts.value, "max-results": Number(document.querySelector("#limit").value) };
    if (folders.value) arguments_.folder = folders.value;
    if (searching === true) arguments_.query = document.querySelector("#query").value;
    else arguments_.unread = document.querySelector("#unread").checked;
    return ui.run(document.querySelector(searching === true ? "#search" : "#refresh"),
      () => ClawApp.call(searching === true ? "search" : "list", arguments_),
      (result) => { if (request === generation) list(result); }, notice);
  }
  accounts.onchange = () => {
    const request = ++generation;
    resetMessage();
    folders.replaceChildren();
    document.querySelector("#messages").replaceChildren();
    document.querySelector("#draft").hidden = true;
    const item = accountItems.get(accounts.value);
    document.querySelector("#compose").disabled = !item || !item.can_send ||
      !(ClawApp.tool(app, "draft_save") || ClawApp.tool(app, "send"));
    if (ClawApp.tool(app, "folders") && item) void ui.run(null, () => ClawApp.call("folders", { account: item.id }), (result) => {
      if (request !== generation) return;
      folderItems = ui.rows(result, ["folders"]);
      ui.replace(folders, folderItems.map((entry) => ui.node("option", entry.name || entry.id, { value: entry.id })));
      const inbox = folderItems.find((entry) => entry.special_use && entry.special_use.includes("inbox"));
      if (inbox) folders.value = inbox.id;
      void load();
    }, notice);
  };
  folders.onchange = () => { void load(); };
  document.querySelector("#refresh").onclick = () => { void load(); };
  document.querySelector("#unread").onchange = () => { void load(); };
  document.querySelector("#limit").onchange = () => { void load(); };
  document.querySelector("#search").disabled = !ClawApp.tool(app, "search");
  document.querySelector("#search").onclick = () => { void load(true); };
  document.querySelector("#query").onkeydown = (event) => {
    if (event.key === "Enter" && ClawApp.tool(app, "search")) { event.preventDefault(); void load(true); }
  };
  document.querySelector("#compose").disabled = true;
  document.querySelector("#compose").onclick = () => compose();
  const aiCommands = { summarize: "Summarize message", smart_reply: "Suggest replies",
    smart_compose: "Help compose", translate: "Translate", triage: "Triage", chat: "Ask about mail", draft: "Draft from context" };
  for (const [command, label] of Object.entries(aiCommands)) {
    if (!ClawApp.tool(app, command)) continue;
    const button = ui.node("button", label);
    button.onclick = () => ui.command(app, command, {
      body: document.querySelector("#ai-input").value, context: document.querySelector("#ai-input").value,
      subject: selected && selected.subject, sender: selected && selected.from,
    }, aiResult, { title: label, submitLabel: label, fields: {
      subject: fields.subject, body: fields.body, context: { label: "Writing context", type: "textarea", rows: 8 },
      sender: { label: "Message sender", type: "text" }, lang: { label: "Output language", type: "text" },
      question: { label: "Your question", type: "textarea" }, intent: { label: "What do you want to say?", type: "textarea" },
    } });
    document.querySelector("#ai-actions").append(button);
  }
  document.querySelector("#ai").hidden = !document.querySelector("#ai-actions").children.length;
  ui.allTools(document.querySelector("#more"), app, (value) => ui.output(document.querySelector("#ai-result"), value), defaults);
  if (ClawApp.tool(app, "accounts")) void ui.run(null, () => ClawApp.call("accounts"), (result) => {
    const values = ui.rows(result, ["accounts", "items"]);
    for (const item of values) accountItems.set(item.id, item);
    ui.replace(accounts, values.map((item) => ui.node("option", item.name || item.label || item.id, { value: item.id || item.account })));
    if (values.length) accounts.onchange();
    else notice.textContent = "No Thunderbird accounts are configured. Add an account in Thunderbird before opening a mailbox.";
  }, notice);
  else {
    document.querySelector("#mail-toolbar").hidden = true;
    document.querySelector("#mailbox").hidden = true;
    notice.textContent = "Mail AI processes only the content you supply. It does not read another App's mailbox.";
  }
});
