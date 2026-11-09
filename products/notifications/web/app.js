ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const $ = (selector) => document.querySelector(selector);
  const has = (command) => Boolean(ClawApp.tool(app, command));
  const native = app.id === "cosmic-notifications";
  const durableId = /^notif-[a-fA-F0-9]{32}$/;
  let busy = false;
  let records = [];
  let total = 0;
  let loaded = false;
  const receipts = [];
  ui.showApp(app);

  function call(command, args) {
    const tool = ClawApp.tool(app, command);
    if (!tool) throw new Error(`This entry does not declare ${command}.`);
    return ClawApp.call(tool.name, args);
  }
  function checked(value) {
    ui.output($("#raw"), value);
    if (value && value.error) throw new Error(String(value.error));
    return value;
  }
  function update() {
    $("#refresh").disabled = busy || !has("list");
    $("#send-button").disabled = busy || !has(native ? "post" : "send");
    const text = native ? $("#body").value : $("#message").value;
    $("#characters").textContent = native ? `${Array.from($("#summary").value).length} / 240 headline characters; ${Array.from(text).length} / 4000 body characters` :
      `${Array.from(text).length} / 4000 message characters`;
  }
  async function perform(action, render, failed) {
    if (busy) return;
    busy = true;
    const controls = Array.from(document.querySelectorAll("button, input, textarea")).filter((control) => !control.disabled);
    controls.forEach((control) => { control.disabled = true; });
    const result = await ui.run(null, async () => checked(await action()), render, $("#notice"));
    if (result === undefined && failed) failed();
    busy = false;
    controls.forEach((control) => { control.disabled = false; });
    update();
  }
  function utc(value) {
    if (!value) return "Timestamp not provided";
    return `${value}${/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$/.test(value) ? " UTC" : ""}`;
  }
  function renderRecords() {
    const filter = $("#filter").value.trim().toLowerCase();
    const source = native ? receipts : records;
    const visible = source.filter((entry) => {
      if (!native && $("#unread").checked && entry.read !== false) return false;
      return `${entry.id} ${entry.message || entry.summary || ""} ${entry.body || ""}`.toLowerCase().includes(filter);
    });
    $("#total").textContent = native ? `${visible.length} / ${receipts.length} post receipts held in this page (not a service history list).` :
      loaded ? `${records.length} fetched of ${total} retained unexpired records in this entry's source scope; ${visible.length} match this view.` :
        "No authoritative source list loaded.";
    ui.replace($("#notifications"), visible.map((entry) => {
      const card = ui.node("article", null, { class: "card stack" });
      card.append(ui.node("h3", native ? entry.summary : entry.urgent ? "Urgent notification" : "Notification", { class: "prose" }),
        ui.node("p", native ? entry.body || "(no body)" : entry.message, { class: "prose" }),
        ui.node("p", entry.id, { class: "code" }));
      if (native) {
        card.append(ui.node("p", entry.dismissed ? "Dismissed - confirmed by the close response; not an acknowledgement." :
          entry.closeRequested ? "Dismissal requested; its result is not confirmed." :
            "Durable ID returned; delivery and read state were not provided.", { class: "muted small" }));
        card.append(ui.node("p", `Local receipt time: ${entry.received}`, { class: "muted small" }));
        if (has("close") && !entry.dismissed && !entry.closeRequested) {
          const button = ui.node("button", "Review dismissal", { type: "button" });
          button.onclick = () => closeDialog(entry.id);
          card.append(button);
        }
      } else {
        card.append(ui.node("span", `State: ${entry.state || "not reported"} - ${
          entry.read === false ? "unread" : entry.read === true ? "read flag set" : "read flag not reported"}`, { class: "pill" }),
        ui.node("p", utc(entry.timestamp), { class: "muted small" }));
      }
      return card;
    }));
    if (!visible.length) ui.replace($("#notifications"), [ui.node("p",
      source.length ? "No loaded entries match the current filters." : native ?
        "No native post responses in this page. This entry has no history-list tool." :
        loaded ? "The service returned no records for this source." : "Load source history to see authoritative records.", { class: "empty" })]);
  }
  function refresh() {
    if (busy || !has("list")) return;
    const limit = Number($("#limit").value);
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
      $("#notice").textContent = "Fetch limit must be an integer from 1 to 100.";
      $("#notice").classList.add("error");
      return;
    }
    $("#list-state").textContent = "Loading the owning entry's source history...";
    void perform(() => call("list", { limit }), (value) => {
      if (!Array.isArray(value.notifications) || !Number.isInteger(value.total) || value.total < 0) {
        throw new Error("The service returned no valid notification history.");
      }
      records = value.notifications;
      total = value.total;
      loaded = true;
      $("#list-state").textContent = `Source history refreshed locally at ${new Date().toLocaleTimeString()}. Delivery does not set read.`;
      renderRecords();
    }, () => {
      $("#list-state").textContent = loaded ? "Refresh failed. Entries below are from the last successful source observation, not current state." :
        "Source history is unavailable; an empty history is not inferred.";
    });
  }
  function closeDialog(id) {
    if (busy || !has("close") || !durableId.test(id)) return;
    ui.command(app, "close", { id }, (value) => {
      checked(value);
      if (value.ok !== true || value.id !== id || value.state !== "dismissed") {
        throw new Error("The service did not confirm dismissal. No read or acknowledgement is inferred.");
      }
      const entry = receipts.find((receipt) => receipt.id === id);
      if (entry) { entry.dismissed = true; entry.closeRequested = false; }
      $("#outcome").textContent = `Service confirmed dismissal of ${id}. Dismissal is not acknowledgement.`;
      renderRecords();
    }, {
      title: "Dismiss this native notification", submitLabel: "Dismiss notification",
      description: "Requests dismissal of this exact durable record and its desktop presentation. Only the same authenticated owner/native source can close it. No delivery, read or acknowledgement is fabricated.",
      fields: { id: { label: "Native durable notification ID", type: "text", readOnly: true } },
    });
    document.querySelector("dialog form").addEventListener("submit", () => {
      const entry = receipts.find((receipt) => receipt.id === id);
      if (entry) entry.closeRequested = true;
      $("#outcome").textContent = `Dismissal requested once for ${id}; an unknown result must not be blindly retried.`;
      renderRecords();
    });
  }
  function validateText(value, label, max, optional, multiline) {
    if (!optional && !value.trim() || Array.from(value).length > max ||
        (!multiline && /[\u0000-\u001f\u007f-\u009f]/.test(value)) ||
        (multiline && /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/.test(value))) {
      throw new Error(`${label} must be ${optional ? "empty or " : ""}valid plain text of at most ${max} characters.`);
    }
  }

  $("#scope").textContent = native ?
    "Native notification posts and same-source dismissal only. This entry has no list, acknowledgement or owner-wide notification authority. Display labels never change producer identity." :
    "Only your notify-produced OS records are listed. Native, other-App/task records and historical JSON are excluded. Read state is authoritative and cannot be changed through this entry.";
  $("#list-title").textContent = native ? "Native posts observed in this page" : "Your notify source history";
  $("#compose-help").textContent = native ?
    "Headline: 1..240 characters. Optional body: up to 4000. Popup timeout and transient affect presentation only, not durable OS activity." :
    "Send 1..4000 plain-text characters. Urgent maps to warning severity and respects DND/channel preferences; it does not bypass them.";
  $("#refresh").hidden = !has("list");
  $("#limit-label").hidden = !has("list");
  $("#unread-label").hidden = native;
  $("#message-label").hidden = native;
  $("#urgent-label").hidden = native;
  $("#message").required = !native;
  $("#message").disabled = native;
  $("#urgent").disabled = native;
  $("#summary-label").hidden = !native;
  $("#body-label").hidden = !native;
  $("#summary").required = native;
  for (const selector of ["#summary", "#body", "#sender", "#icon", "#expiry", "#transient", "#dedupe"]) $(selector).disabled = !native;
  $("#post-options").hidden = !native;
  $("#close-form").hidden = !has("close");
  $("#send-button").textContent = native ? "Post notification" : "Send notification";
  $("#filter").oninput = renderRecords;
  $("#unread").onchange = renderRecords;
  for (const selector of ["#summary", "#body", "#message"]) $(selector).oninput = update;
  $("#refresh").onclick = refresh;
  $("#send").onsubmit = (event) => {
    event.preventDefault();
    if (busy || !$("#send").reportValidity()) return;
    let args;
    try {
      if (native) {
        validateText($("#summary").value, "Headline", 240, false, false);
        validateText($("#body").value, "Body", 4000, true, true);
        if ($("#body").value && !$("#body").value.trim()) throw new Error("A supplied body must contain non-whitespace text.");
        const sender = $("#sender").value || "Claw OS Agent";
        validateText(sender, "Display sender", 128, false, false);
        const expiry = Number($("#expiry").value);
        if ($("#expiry").value === "" || !Number.isInteger(expiry) || expiry < -1 || expiry > 2147483647) {
          throw new Error("Popup timeout must be -1, 0, or a positive signed 32-bit integer.");
        }
        args = { summary: $("#summary").value, body: $("#body").value, app_name: sender, icon: $("#icon").value,
          expire_ms: expiry, transient: $("#transient").checked };
        if ($("#dedupe").value) args.dedupe_key = $("#dedupe").value;
      } else {
        validateText($("#message").value, "Message", 4000, false, true);
        args = { message: $("#message").value, urgent: $("#urgent").checked };
      }
    } catch (error) {
      $("#notice").textContent = error.message;
      $("#notice").classList.add("error");
      return;
    }
    $("#outcome").textContent = "Sending once. If no durable ID is confirmed, preserve this message and inspect state before retrying.";
    void perform(() => call(native ? "post" : "send", args), (value) => {
      if (!durableId.test(value?.id)) throw new Error("No valid durable notification ID was returned. The send outcome is unconfirmed.");
      $("#receipt").textContent = `Durable ID: ${value.id}${value.timestamp ? `\nCreated: ${utc(value.timestamp)}` : ""}\nDelivery/read/acknowledgement are not confirmed by this receipt.`;
      $("#outcome").textContent = "Durable notification ID returned. No file, DND preference or read state was changed by this view.";
      if (native) {
        const entry = { id: value.id, summary: args.summary, body: args.body, received: new Date().toLocaleTimeString() };
        const index = receipts.findIndex((receipt) => receipt.id === entry.id);
        if (index >= 0) receipts.splice(index, 1);
        receipts.unshift(entry);
        receipts.splice(50);
        $("#summary").value = "";
        $("#body").value = "";
        renderRecords();
      } else {
        $("#message").value = "";
        $("#list-state").textContent = "A send receipt was returned. Refresh source history for its authoritative state; the list has not been synthesized.";
      }
    });
  };
  $("#close-form").onsubmit = (event) => {
    event.preventDefault();
    if ($("#close-form").reportValidity()) closeDialog($("#close-id").value);
  };
  renderRecords();
  update();
  if (has("list")) refresh();
});
