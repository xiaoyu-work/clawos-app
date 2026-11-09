ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const $ = (id) => document.getElementById(id);
  let busy = false;
  let reviewing = false;
  ui.showApp(app);
  if (app.id !== "gateway-homeassistant") { ui.replace($("workspace"), [ui.node("p", "This entry has no Home Assistant adapter.", { class: "empty" })]); return; }

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
  async function request(button, command, args, done, notice = $("notice")) {
    if (busy) return;
    busy = true;
    try {
      await ui.run(button, async () => {
        const tool = ClawApp.tool(app, command);
        if (!tool) throw new Error(`This App does not declare ${command}.`);
        const value = await ClawApp.call(tool.name, args);
        if (value && value.ok === false) throw new Error(value.error || "Home Assistant refused the request.");
        return value;
      }, done, notice);
    } finally { busy = false; }
  }
  function service(value, notification = false) {
    value = value.trim();
    if (value === "notify") return value;
    if (!/^[a-z0-9_]+\.[a-z0-9_]+$/.test(value) || notification && !value.startsWith("notify.")) throw new Error(notification ? "Choose an explicit notify service, such as notify.mobile_app_phone or notify." : "Use an explicit domain.service name.");
    return value;
  }
  function review(command, args, summary) {
    if (busy || reviewing) return;
    reviewing = true;
    const dialog = ui.node("dialog"); const form = ui.node("form");
    const check = ui.node("input", null, { type: "checkbox", required: "" });
    const label = ui.node("label", "I confirm this external service action and its exact targets."); label.append(check);
    const notice = ui.node("p", "", { class: "notice", role: "status", "aria-live": "polite" });
    const cancel = ui.node("button", "Cancel", { type: "button" });
    const execute = ui.node("button", command === "send" ? "Send notification once" : "Call service once", { type: "submit", class: "primary" });
    const actions = ui.node("div", null, { class: "toolbar" }); actions.append(cancel, execute);
    form.append(ui.node("p", "This can operate real devices or automations on the configured server. Service acceptance does not prove a device reached a requested state."), detail(summary), label, notice, actions);
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (!check.checked || busy) return;
      cancel.disabled = true;
      await request(execute, command, args, (value) => {
        $("result-title").textContent = `Service response: ${args.service} (device state not verified)`;
        ui.replace($("result"), [detail(value)]);
        $("notice").textContent = "Request returned. No device-state polling, automation or automatic retry was started.";
        dialog.close();
      }, notice);
      cancel.disabled = false; check.checked = false;
      if (dialog.open) notice.append(ui.node("span", " The action may have completed. Check Home Assistant before retrying."));
    };
    cancel.onclick = () => dialog.close();
    dialog.addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
    dialog.addEventListener("close", () => { reviewing = false; dialog.remove(); });
    dialog.append(ui.node("h2", "Review Home Assistant action"), form); document.body.append(dialog); dialog.showModal();
  }
  $("status-button").onclick = (event) => void request(event.currentTarget, "status", {}, (value) => {
    ui.replace($("configuration"), [ui.node("p", value && value.configured === true ? "Configuration available; server reachability has not been tested." : "Configuration is missing or unavailable. No server request was made."), detail(value)]);
  });
  $("notify-form").onsubmit = (event) => {
    event.preventDefault();
    try {
      const args = { service: service($("notify-service").value, true), text: $("message").value };
      if (!args.text.trim()) throw new Error("Enter a notification message.");
      if ($("notify-title").value.trim()) args.title = $("notify-title").value.trim();
      review("send", args, args);
    } catch (error) { $("notice").textContent = error.message; }
  };
  $("control-form").onsubmit = (event) => {
    event.preventDefault();
    try {
      const entities = $("entities").value.split(",").map((value) => value.trim()).filter(Boolean);
      if (!entities.length || entities.some((value) => !/^[a-z0-9_]+\.[a-z0-9_]+$/.test(value))) throw new Error("Enter exact entity IDs separated by commas, such as light.kitchen.");
      const payload = { entity_id: entities.length === 1 ? entities[0] : entities };
      const targetService = service($("control-service").value);
      review("call", { service: targetService, json: JSON.stringify(payload) }, { service: targetService, entities });
    } catch (error) { $("notice").textContent = error.message; }
  };
  $("advanced-form").onsubmit = (event) => {
    event.preventDefault();
    try {
      const targetService = service($("custom-service").value);
      const payload = JSON.parse($("payload").value);
      if (!payload || Array.isArray(payload) || typeof payload !== "object") throw new Error("Service data must be a JSON object, not an array or scalar.");
      review("call", { service: targetService, json: JSON.stringify(payload) }, { service: targetService, service_data: payload });
    } catch (error) { $("notice").textContent = error.message; }
  };
}).catch((error) => {
  document.getElementById("notice").textContent = `Home Integration UI unavailable: ${error.message}`;
});
