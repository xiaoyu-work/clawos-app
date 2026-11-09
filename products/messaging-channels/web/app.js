ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const $ = (id) => document.getElementById(id);
  const platform = {
    "gateway-discord": { name: "Discord", recipient: "Channel ID", argument: "channel_id", repeatable: true, credential: "discord_bot_token" },
    "gateway-telegram": { name: "Telegram", recipient: "Chat ID", argument: "chat_id", repeatable: true, limit: 4096, credential: "telegram_bot_token" },
    "gateway-slack": { name: "Slack", recipient: "Channel ID", argument: "channel_id", limit: 4000, credential: "slack_bot_token" },
    "gateway-whatsapp": { name: "WhatsApp", recipient: "Recipient phone number (E.164)", argument: "recipient_phone", limit: 4096, credential: "whatsapp_access_token and whatsapp_phone_number_id" },
  }[app.id];
  let busy = false;
  let reviewing = false;
  ui.showApp(app);
  if (!platform) { ui.replace($("workspace"), [ui.node("p", "This identity has no supported messaging channel.", { class: "empty" })]); return; }
  $("title").textContent = `${platform.name} Channel`;
  $("recipient-label").firstChild.textContent = platform.recipient;
  $("recipient").placeholder = app.id === "gateway-whatsapp" ? "+15551234567" : app.id === "gateway-telegram" ? "Exact chat ID or supported chat name" : "Exact provider channel ID";
  $("credential-note").textContent = `Outbound credentials: ${platform.credential}, through this App's existing OS configuration and environment precedence. This page never edits or stores tokens.`;
  $("send-note").textContent = platform.limit ? `Messages are limited here to ${platform.limit} characters to avoid adapter truncation.` : "Discord splits long text into multiple remote messages and disables mentions. A partial submission must not be resent automatically.";

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
  function evidence(title, value) {
    $("result-title").textContent = title;
    ui.replace($("result"), [detail(value)]);
  }
  async function request(control, command, args, done, notice = $("notice")) {
    if (busy) return;
    busy = true;
    try {
      await ui.run(control, async () => {
        const tool = ClawApp.tool(app, command);
        if (!tool) throw new Error(`This entry does not declare ${command}.`);
        const value = await ClawApp.call(tool.name, args);
        if (value && value.ok === false) throw new Error(value.error || "The channel service refused the request.");
        return value;
      }, done, notice);
    } finally { busy = false; }
  }
  function review(command, args, title, explanation, summary = args) {
    if (busy || reviewing) return;
    reviewing = true;
    const dialog = ui.node("dialog"); const form = ui.node("form");
    const check = ui.node("input", null, { type: "checkbox", required: "" });
    const label = ui.node("label", "I confirm this action using only this channel App's authority."); label.append(check);
    const notice = ui.node("p", "", { class: "notice", role: "status", "aria-live": "polite" });
    const cancel = ui.node("button", "Cancel", { type: "button" });
    const execute = ui.node("button", title, { type: "submit", class: "primary" });
    const actions = ui.node("div", null, { class: "toolbar" }); actions.append(cancel, execute);
    form.append(ui.node("p", explanation), detail(summary), label, notice, actions);
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (!check.checked || busy) return;
      cancel.disabled = true;
      const callArgs = command === "reply" ? { ...args, confirm: true } : args;
      await request(execute, command, callArgs, (value) => {
        evidence(title, value);
        $("notice").textContent = command === "send" || command === "reply" ?
          "Provider submission evidence is not delivery confirmation. No automatic resend was made." :
          "Request returned. Refresh channel status to inspect the current OS state.";
        dialog.close();
      }, notice);
      cancel.disabled = false; check.checked = false;
      if (dialog.open) notice.append(ui.node("span", " The outcome may be unknown. Inspect OS/provider evidence before retrying; messages are never automatically resent."));
    };
    cancel.onclick = () => dialog.close();
    dialog.addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
    dialog.addEventListener("close", () => { reviewing = false; dialog.remove(); });
    dialog.append(ui.node("h2", title), form); document.body.append(dialog); dialog.showModal();
  }
  $("status").onclick = (event) => void request(event.currentTarget, "status", {}, (value) => {
    const running = value && typeof value.running === "boolean" ? value.running ? "Receiver reported running." : "Receiver reported not running." : "Receiver running state was not reported.";
    ui.replace($("state"), [ui.node("p", running), detail(value)]);
  });
  $("start").onclick = () => review("start", {}, `Start ${platform.name} receiver`, "The OS must already have an authenticated provider/account/sender binding to an existing Activity trigger. Starting cannot create a trigger or grant Agent authority. Initial polling establishes an inert baseline, not backlog replay.");
  $("stop").onclick = () => review("stop", {}, `Stop ${platform.name} receiver`, "Stop new inbound admission for this configured channel. Already-published events, Jobs and provider submissions are not cancelled or rolled back.");
  $("send-form").onsubmit = (event) => {
    event.preventDefault();
    try {
      let recipient = $("recipient").value.trim();
      const text = $("text").value;
      if (!recipient || /[\u0000-\u001f]/.test(recipient)) throw new Error("Enter an exact provider recipient.");
      if (!text.trim()) throw new Error("Enter message text.");
      if (app.id === "gateway-discord" && !/^[0-9]{1,20}$/.test(recipient)) throw new Error("Discord channel ID must be a 1-20 digit snowflake.");
      if (platform.limit && Array.from(text).length > platform.limit) throw new Error(`Keep the message within ${platform.limit} characters to avoid truncation.`);
      if (app.id === "gateway-whatsapp") {
        if (!/^\+?[0-9\s()-]+$/.test(recipient)) throw new Error("Direct WhatsApp send needs a phone number. Opaque BSUID recipients belong only to verified receipt-bound replies.");
        recipient = recipient.replace(/[^0-9]/g, "");
        if (!recipient) throw new Error("Recipient phone must contain digits.");
      }
      const args = { [platform.argument]: recipient, text: platform.repeatable ? [text] : text };
      review("send", args, `Send ${platform.name} message once`, "This is a new outbound provider submission to the exact recipient, independent of receiver admission. It is not a response to an inbound event.", { recipient, message: text });
    } catch (error) { $("notice").textContent = error.message; }
  };
  $("reply-form").onsubmit = (event) => {
    event.preventDefault();
    try {
      const eventId = $("event-id").value.trim();
      const text = $("reply-text").value;
      if (!eventId || /[\u0000-\u001f]/.test(eventId)) throw new Error("Paste a verified event ID from the OS channel evidence.");
      if (!text.trim()) throw new Error("Enter reply text.");
      review("reply", { event_id: eventId, text: [text] }, `Reply through ${platform.name} receipt`, "The OS resolves the original owner/account/recipient/thread, binding and reply window. No recipient override is sent. An uncertain reply is held, never automatically resubmitted.", { verified_event_id: eventId, message: text, recipient: "Resolved only by the OS receipt; opaque WhatsApp identifiers stay unchanged" });
    } catch (error) { $("notice").textContent = error.message; }
  };
  for (const [inputId, countId] of [["text", "send-count"], ["reply-text", "reply-count"]]) {
    $(inputId).oninput = () => { $(countId).textContent = `${Array.from($(inputId).value).length} characters. Editing does not send anything.`; };
  }
  $("legacy").hidden = app.id !== "gateway-discord";
  if (app.id === "gateway-discord") {
    $("legacy-form").onsubmit = (event) => {
      event.preventDefault();
      try {
        function ids(id, required) {
          const values = $(id).value.split(",").map((value) => value.trim()).filter(Boolean);
          if (required && !values.length || values.some((value) => !/^[0-9]{1,20}$/.test(value))) throw new Error("Preference lists require exact comma-separated Discord IDs; at least one user is required.");
          return values.join(",");
        }
        const settings = [`allowed_users=${ids("legacy-users", true)}`];
        const guilds = ids("legacy-guilds", false); const channels = ids("legacy-channels", false);
        if (guilds) settings.push(`allowed_guilds=${guilds}`);
        if (channels) settings.push(`allowed_channels=${channels}`);
        const rpm = Number($("legacy-rpm").value);
        if (!Number.isInteger(rpm) || rpm < 1 || rpm > 60) throw new Error("Requests per minute must be 1-60.");
        settings.push(`require_mention=${$("legacy-mention").value}`, `requests_per_minute=${rpm}`);
        review("configure", { settings }, "Save legacy Discord preferences", "These are App-local, non-authoritative preferences, not current Root admission settings. They do not configure, start or authorize ingress. Blank optional lists are left unchanged.", { preference_updates: settings });
      } catch (error) { $("notice").textContent = error.message; }
    };
  }
}).catch((error) => {
  document.getElementById("notice").textContent = `Channel UI unavailable: ${error.message}`;
});
