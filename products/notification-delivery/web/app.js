ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const root = document.getElementById("workspace");
  const notice = document.getElementById("notice");
  const names = { "gateway-ntfy": "ntfy", "gateway-pushover": "Pushover", "gateway-webhook": "Webhook" };
  const name = names[app.id];
  let busy = false;
  let reviewing = false;
  ui.showApp(app);
  if (!name) { root.append(ui.node("p", "This identity has no supported delivery interface.", { class: "empty" })); return; }
  document.getElementById("title").textContent = `${name} Delivery`;

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
  function section(title, text) {
    const card = ui.node("section", null, { class: "card stack" });
    card.append(ui.node("h2", title), ui.node("p", text)); root.append(card); return card;
  }
  function field(parent, label, attributes = {}, tag = "input") {
    const row = ui.node("label", label); const input = ui.node(tag, null, attributes);
    row.append(input); parent.append(row); return input;
  }
  function choose(parent, label, choices) {
    const select = field(parent, label, {}, "select");
    for (const [value, text] of choices) select.append(ui.node("option", text, { value }));
    return select;
  }
  function httpUrl(value, label) {
    let url;
    try { url = new URL(value); } catch { throw new Error(`${label} must be an absolute HTTP or HTTPS URL.`); }
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.hash) throw new Error(`${label} must use HTTP(S), without embedded credentials or a fragment.`);
    return value;
  }
  function optional(args, name, input) {
    if (input.value.trim()) args[name] = input.value.trim();
  }
  async function request(control, command, args, done, status = notice) {
    if (busy) return;
    busy = true;
    try {
      await ui.run(control, async () => {
        const tool = ClawApp.tool(app, command);
        if (!tool) throw new Error(`This entry does not declare ${command}.`);
        const value = await ClawApp.call(tool.name, args);
        if (value && value.ok === false) throw new Error(value.error || (Array.isArray(value.errors) ? value.errors.join("; ") : "The provider did not accept the request."));
        return value;
      }, done, status);
    } finally { busy = false; }
  }
  function review(args, summary) {
    if (busy || reviewing) return;
    reviewing = true;
    const dialog = ui.node("dialog"); const form = ui.node("form");
    const check = ui.node("input", null, { type: "checkbox", required: "" });
    const label = ui.node("label", "I confirm sending this message to the destination shown."); label.append(check);
    const status = ui.node("p", "", { class: "notice", role: "status", "aria-live": "polite" });
    const cancel = ui.node("button", "Cancel", { type: "button" });
    const execute = ui.node("button", "Send once", { type: "submit", class: "primary" });
    const actions = ui.node("div", null, { class: "toolbar" }); actions.append(cancel, execute);
    form.append(ui.node("p", "This is an external, one-shot submission. There is no local queue, DND integration, delivery acknowledgement or automatic retry."), detail(summary), label, status, actions);
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (!check.checked || busy) return;
      cancel.disabled = true;
      await request(execute, "send", args, (value) => {
        document.getElementById("result-title").textContent = value && value.ok === true ? "Submission accepted by provider (not delivery confirmation)" : "Provider response (outcome not confirmed)";
        ui.replace(document.getElementById("result"), [detail(value)]);
        notice.textContent = "The request was not automatically repeated. A receipt or message ID is not a delivery or acknowledgement guarantee.";
        dialog.close();
      }, status);
      cancel.disabled = false; check.checked = false;
      if (dialog.open) status.append(ui.node("span", " Submission may be uncertain. Check the provider before manually sending again."));
    };
    cancel.onclick = () => dialog.close();
    dialog.addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
    dialog.addEventListener("close", () => { reviewing = false; dialog.remove(); });
    dialog.append(ui.node("h2", `Review ${name} delivery`), form); document.body.append(dialog); dialog.showModal();
  }

  const config = section(`${name} configuration`, "Configuration checks only report this App's stored setup; they are not a reachability test. Credentials are managed by the OS, not saved in this page.");
  const configResult = ui.node("div", "Configuration has not been checked.", { class: "muted" });
  let statusArgs = () => ({});
  let composeArgs;
  const formCard = section("Compose a delivery", "Only the loaded App's outbound tool is used. Delivery does not borrow another App's consent, budget or credentials.");
  const form = ui.node("form"); formCard.append(form);
  const text = field(form, "Message", { required: "", rows: "5", placeholder: "Message to publish" }, "textarea");
  const title = app.id !== "gateway-webhook" ? field(form, "Title (optional)", { maxlength: app.id === "gateway-pushover" ? "250" : "512" }) : null;
  const counter = ui.node("p", "", { class: "muted small" }); form.append(counter);
  text.oninput = () => { counter.textContent = `${Array.from(text.value).length} characters. No message is sent while editing.`; };

  if (app.id === "gateway-ntfy") {
    const server = field(config, "Server URL (required for send and status)", { type: "url", placeholder: "https://ntfy.sh", required: "", autocomplete: "off" });
    const topic = field(form, "Topic (optional if an OS default is configured)", { placeholder: "Exact topic name", autocomplete: "off" });
    const priority = choose(form, "Priority", [["", "Provider default"], ["min", "Minimum"], ["low", "Low"], ["default", "Default"], ["high", "High"], ["max", "Maximum"], ["urgent", "Urgent"]]);
    const advanced = ui.node("details", null, { class: "stack" }); advanced.append(ui.node("summary", "Message options"));
    const tags = field(advanced, "Tags (comma-separated, optional)", { placeholder: "information,package" });
    const click = field(advanced, "Click URL (optional)", { type: "url", placeholder: "https://example.org/details" });
    const markdown = field(advanced, "Ask ntfy to render Markdown", { type: "checkbox" });
    form.append(advanced);
    config.append(ui.node("p", "Optional OS values: ntfy_default_topic and ntfy_token. The stored token is not used for the public https://ntfy.sh server. Per-request plaintext authentication overrides are not collected here.", { class: "muted small" }));
    statusArgs = () => ({ server: httpUrl(server.value.trim(), "Server") });
    composeArgs = () => {
      if (Array.from(text.value).length > 4000) throw new Error("Keep the message within 4000 characters to avoid the adapter's truncation.");
      const args = { ...statusArgs(), text: text.value, markdown: markdown.checked };
      optional(args, "topic", topic); optional(args, "title", title); optional(args, "priority", priority); optional(args, "tags", tags);
      if (click.value.trim()) args.click = httpUrl(click.value.trim(), "Click URL");
      for (const key of ["topic", "title", "tags"]) if (args[key] && /[\r\n]/.test(args[key])) throw new Error(`${key} cannot contain line breaks.`);
      return { args, summary: { ...args, topic: args.topic || "OS-configured default topic (not selected by this page)" } };
    };
  } else if (app.id === "gateway-pushover") {
    config.append(ui.node("p", "The owning App uses pushover_app_token and pushover_user_key, with its existing environment precedence. This UI neither reads their plaintext nor changes them.", { class: "muted small" }));
    const priority = choose(form, "Priority", [["", "Provider default"], ["-2", "Lowest (-2)"], ["-1", "Low (-1)"], ["0", "Normal (0)"], ["1", "High (1)"], ["2", "Emergency (2; provider repeats until expiry)"]]);
    const emergency = ui.node("div", null, { class: "stack", hidden: "" });
    emergency.append(ui.node("p", "Emergency retries happen at Pushover, not in this App. A receipt does not prove acknowledgement.", { class: "danger small" }));
    const retry = field(emergency, "Provider retry interval (seconds, at least 30)", { type: "number", min: "30", step: "1", value: "60" });
    const expire = field(emergency, "Provider expiry (seconds, at most 10800)", { type: "number", min: "1", max: "10800", step: "1", value: "3600" });
    priority.onchange = () => { emergency.hidden = priority.value !== "2"; };
    form.append(emergency);
    const advanced = ui.node("details", null, { class: "stack" }); advanced.append(ui.node("summary", "Recipient and message options"));
    const recipient = field(advanced, "Recipient user/group key override (optional; otherwise configured default)", { type: "password", autocomplete: "off" });
    const device = field(advanced, "Recipient device names (optional)", { placeholder: "Comma-separated Pushover device names" });
    const sound = field(advanced, "Sound name (optional)", { placeholder: "Provider sound name" });
    const url = field(advanced, "Supplementary URL (optional)", { type: "url", maxlength: "512" });
    const urlTitle = field(advanced, "URL title (optional)", { maxlength: "100" });
    const ttl = field(advanced, "Device auto-deletion TTL in seconds (optional)", { type: "number", min: "0", step: "1" });
    const html = field(advanced, "Ask Pushover to render its supported HTML subset", { type: "checkbox" });
    form.append(advanced);
    composeArgs = () => {
      if (Array.from(text.value).length > 1024) throw new Error("Keep the message within 1024 characters to avoid Pushover truncation.");
      const args = { text: text.value, html: html.checked };
      optional(args, "title", title); optional(args, "recipient", recipient); optional(args, "device", device); optional(args, "sound", sound); optional(args, "url_title", urlTitle);
      if (priority.value !== "") args.priority = Number(priority.value);
      if (url.value.trim()) args.url = httpUrl(url.value.trim(), "Supplementary URL");
      if (ttl.value !== "") {
        args.ttl = Number(ttl.value);
        if (!Number.isSafeInteger(args.ttl) || args.ttl < 0) throw new Error("TTL must be a non-negative integer.");
      }
      if (args.priority === 2) {
        args.retry = Number(retry.value); args.expire = Number(expire.value);
        if (!Number.isSafeInteger(args.retry) || args.retry < 30 || !Number.isInteger(args.expire) || args.expire < 1 || args.expire > 10800) throw new Error("Emergency priority requires retry >=30 and expiry from 1 to 10800 seconds.");
      }
      return { args, summary: { ...args, recipient: args.recipient ? "Explicit recipient key override (hidden)" : "OS-configured default user/group" } };
    };
  } else {
    config.append(ui.node("p", "The App uses webhook_default_url and optional webhook_default_secret (HMAC), with its existing environment precedence. Authentication overrides remain outside this composer; no secret is persisted here.", { class: "muted small" }));
    const target = field(form, "Target URL (optional; blank uses the OS-configured default)", { type: "url", placeholder: "https://example.org/hook", autocomplete: "off" });
    const format = choose(form, "Body format", [["json", "JSON message envelope (text, platform, timestamp)"], ["raw", "Raw UTF-8 text"]]);
    composeArgs = () => {
      const args = { text: text.value, raw: format.value === "raw" };
      if (target.value.trim()) args.target = httpUrl(target.value.trim(), "Target");
      return { args, summary: { destination: args.target || "OS-configured default URL (not disclosed by status)", format: args.raw ? "text/plain UTF-8" : "JSON envelope generated by the adapter", message: args.text, authentication: "Existing App configuration; default HMAC secret if configured" } };
    };
  }
  const statusButton = ui.node("button", "Check configuration", { type: "button" });
  statusButton.onclick = () => {
    try { void request(statusButton, "status", statusArgs(), (value) => ui.replace(configResult, [detail(value)])); }
    catch (error) { notice.textContent = error.message; }
  };
  config.append(statusButton, configResult);
  const submit = ui.node("button", "Review delivery...", { type: "submit", class: "primary" }); form.append(submit);
  form.onsubmit = (event) => {
    event.preventDefault();
    try {
      if (!text.value.trim()) throw new Error("Enter a non-empty message.");
      const { args, summary } = composeArgs();
      review(args, summary);
    } catch (error) { notice.textContent = error.message; }
  };
}).catch((error) => {
  document.getElementById("notice").textContent = `Delivery UI unavailable: ${error.message}`;
});
