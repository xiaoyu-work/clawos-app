ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const $ = (id) => document.getElementById(id);
  ui.showApp(app);
  let busy = false;
  let reviewing = false;

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
        const cell = ui.node("dd");
        cell.append(detail(item));
        grid.append(cell);
      }
      if (!grid.children.length) box.append(ui.node("p", "No additional fields returned.", { class: "muted" }));
      box.append(grid);
    }
    return box;
  }
  function device() {
    const value = $("device").value.trim();
    if (!/^\/dev\/[A-Za-z0-9._/+:-]+$/.test(value) || value.split("/").slice(2).some((part) => !part || part === "." || part === "..")) {
      throw new Error("Enter an exact canonical Linux block-device path, such as /dev/sdb1.");
    }
    return value;
  }
  async function request(button, command, args, done, notice = $("notice")) {
    if (busy) return;
    busy = true;
    try {
      await ui.run(button, () => {
        const tool = ClawApp.tool(app, command);
        if (!tool) throw new Error(`This App does not declare ${command}.`);
        return ClawApp.call(tool.name, args);
      }, done, notice);
    } finally { busy = false; }
  }
  function evidence(title, value) {
    $("result-title").textContent = title;
    ui.replace($("result"), [detail(value)]);
  }
  function review(command, title, description) {
    if (reviewing || busy) return;
    let target;
    try { target = device(); } catch (error) { $("notice").textContent = error.message; return; }
    reviewing = true;
    const dialog = ui.node("dialog");
    const form = ui.node("form");
    const check = ui.node("input", null, { type: "checkbox", required: "", name: "acknowledge" });
    const label = ui.node("label", `I want to ${command} ${target}.`);
    label.append(check);
    const notice = ui.node("p", "", { class: "notice", role: "status", "aria-live": "polite" });
    const cancel = ui.node("button", "Cancel", { type: "button" });
    const execute = ui.node("button", title, { type: "submit", class: "primary" });
    const actions = ui.node("div", null, { class: "toolbar" });
    actions.append(cancel, execute);
    form.append(ui.node("p", description), ui.node("p", target, { class: "code" }), label, notice, actions);
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (!check.checked || busy) return;
      cancel.disabled = true;
      await request(execute, command, { device: target }, (value) => {
        evidence(`${title}: ${target}`, value);
        $("notice").textContent = "Response received. Refresh devices before another change; no automatic retry was made.";
        dialog.close();
      }, notice);
      cancel.disabled = false;
      check.checked = false;
      if (dialog.open) notice.append(ui.node("span", " The outcome may be unknown. Inspect device state before retrying."));
    };
    cancel.onclick = () => dialog.close();
    dialog.addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
    dialog.addEventListener("close", () => { reviewing = false; dialog.remove(); });
    dialog.append(ui.node("h2", title), form);
    document.body.append(dialog);
    dialog.showModal();
  }
  function inventory(value) {
    $("device").value = "";
    $("selected").textContent = "No device selected. Selection does not mount, inspect or eject a device.";
    const devices = value && (Array.isArray(value.devices) ? value.devices : Array.isArray(value.blockdevices) ? value.blockdevices : null);
    if (!devices) {
      ui.replace($("devices"), [ui.node("p", "The service did not supply a structured device list. You can enter a known canonical device path below.", { class: "muted" }), detail(value)]);
      return;
    }
    const flat = [];
    function collect(items) {
      for (const item of items) {
        if (!item || typeof item !== "object" || Array.isArray(item)) throw new Error("The storage service returned an unrecognized device record. No device action was taken.");
        flat.push(item);
        if (Array.isArray(item.children)) collect(item.children);
      }
    }
    collect(devices);
    if (!flat.length) {
      ui.replace($("devices"), [ui.node("p", "No devices were returned by the storage service.", { class: "empty" })]);
      return;
    }
    ui.table($("devices"), flat, [
      { label: "Device", value: (item) => item.device || item.path || item.name || "Not reported" },
      { label: "Model", value: (item) => item.model || "Not reported" },
      { label: "Size", value: (item) => item.size ?? "Not reported" },
      { label: "Mount point", value: (item) => Array.isArray(item.mountpoints) ? item.mountpoints.filter(Boolean).join(", ") || "Not mounted" : item.mountpoint || "Not reported" },
    ], { label: "Select", run: (item) => {
      const path = item.device || item.path || (typeof item.name === "string" && item.name.startsWith("/dev/") ? item.name : "");
      $("device").value = path;
      $("selected").textContent = path ? `Selected ${path}. Choose a separate action below.` : "This record has no canonical path. Enter the exact /dev path before continuing.";
      evidence("Selected device record (inventory snapshot)", item);
    } });
  }
  $("refresh").onclick = (event) => void request(event.currentTarget, "status", {}, inventory);
  $("health").onclick = (event) => {
    try {
      const target = device();
      void request(event.currentTarget, "health", { device: target }, (value) => evidence(`Health: ${target}`, value));
    } catch (error) { $("notice").textContent = error.message; }
  };
  $("check").onclick = () => review("check", "Run read-only filesystem check", "The OS only checks supported offline filesystems. It never repairs or formats them. A mounted or unsupported device may be refused.");
  $("mount").onclick = () => review("mount", "Mount device", "Request a mount for this exact device through the OS service. This does not grant file access to other Apps.");
  $("unmount").onclick = () => review("unmount", "Unmount device", "Files on this device may become unavailable. Close users of the mount first.");
  $("eject").onclick = () => review("eject", "Eject device", "The OS may unmount and power off the selected device. Do not remove it until the returned evidence confirms the outcome.");
  if (app.id !== "storage-manager") {
    ui.replace($("workspace"), [ui.node("p", "This interface is only available to the Storage Manager entry.", { class: "empty" })]);
  }
}).catch((error) => {
  document.getElementById("notice").textContent = `Storage UI unavailable: ${error.message}`;
});
