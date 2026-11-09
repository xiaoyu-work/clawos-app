ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const root = document.getElementById("workspace");
  const notice = document.getElementById("notice");
  const names = {
    "accessibility-manager": "Accessibility", "audio-manager": "Audio", "bluetooth-manager": "Bluetooth",
    "camera-manager": "Camera", "display-manager": "Displays", "desktop-manager": "Desktop Windows",
    "location-manager": "Location", "network-manager": "Network", "power-manager": "Power",
    "printer-manager": "Printers", "user-manager": "Users and Groups", "cosmic-settings": "Settings and App Permissions",
  };
  let busy = false;
  let reviewing = false;
  ui.showApp(app);
  document.getElementById("title").textContent = names[app.id] || "Settings";

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
    document.getElementById("result-title").textContent = title;
    ui.replace(document.getElementById("result"), [detail(value)]);
  }
  function section(title, text, parent = root) {
    const card = ui.node("section", null, { class: "card stack" });
    card.append(ui.node("h2", title), ui.node("p", text)); parent.append(card); return card;
  }
  function advanced(title) {
    const box = ui.node("details", null, { class: "card stack" });
    box.append(ui.node("summary", title)); root.append(box); return box;
  }
  function field(parent, label, attributes = {}, tag = "input") {
    const row = ui.node("label", label); const input = ui.node(tag, null, attributes);
    row.append(input); parent.append(row); return input;
  }
  function choose(parent, label, choices, initial = "") {
    const select = field(parent, label, {}, "select");
    for (const entry of choices) {
      const [value, text] = Array.isArray(entry) ? entry : [entry, entry];
      select.append(ui.node("option", text, { value }));
    }
    select.value = initial;
    return select;
  }
  function button(parent, label, action, className = "") {
    const control = ui.node("button", label, { type: "button", class: className });
    control.disabled = false;
    control.onclick = () => { try { action(control); } catch (error) { notice.textContent = error.message; } };
    parent.append(control); return control;
  }
  function text(input, label, maximum = 4096) {
    const value = input.value.trim();
    if (!value || value.length > maximum || /[\u0000-\u001f\u007f-\u009f]/.test(value)) throw new Error(`Enter a valid ${label}, without control characters.`);
    return value;
  }
  function integer(input, label, min, max) {
    const value = Number(input.value);
    if (input.value === "" || !Number.isSafeInteger(value) || value < min || value > max) throw new Error(`${label} must be an integer from ${min} to ${max}.`);
    return value;
  }
  function number(input, label, min, max) {
    const value = Number(input.value);
    if (input.value === "" || !Number.isFinite(value) || value < min || value > max) throw new Error(`${label} must be ${min}-${max}.`);
    return value;
  }
  function path(input, label) {
    const value = text(input, label);
    if (!value.startsWith("/")) throw new Error(`${label} must be an absolute canonical Linux path. The OS rejects symlinks and stale resources.`);
    return value;
  }
  function token(input, label = "Backup token") {
    const value = text(input, label, 32);
    if (!/^[0-9a-fA-F]{32}$/.test(value)) throw new Error(`${label} must be exactly 32 hexadecimal characters.`);
    return value;
  }
  function desired(select) {
    if (!select.value) throw new Error("Choose an explicit desired state. The control is not a readout of current state.");
    return select.value;
  }
  function toggle(parent, label) {
    return choose(parent, label, [["", "Choose desired state"], ["on", "On"], ["off", "Off"]]);
  }
  function list(parent, value, keys, columns, select) {
    const items = keys.map((key) => value && value[key]).find(Array.isArray);
    if (!items) {
      ui.replace(parent, [ui.node("p", "No structured list supplied for this view. Inspect the returned evidence; enter an exact known identifier if needed.", { class: "muted" })]);
      return;
    }
    if (items.some((item) => !item || typeof item !== "object" || Array.isArray(item))) {
      ui.replace(parent, [ui.node("p", "The service returned unrecognized list records. No selection or action was inferred.", { class: "muted" }), detail(items)]);
      return;
    }
    ui.table(parent, items, columns, { label: "Select", run: select });
  }
  async function request(control, command, args, done, status = notice) {
    if (busy) return;
    busy = true;
    try {
      await ui.run(control, async () => {
        const tool = ClawApp.tool(app, command);
        if (!tool) throw new Error(`The loaded ${app.id} entry does not declare ${command}.`);
        const value = await ClawApp.call(tool.name, args);
        if (value && value.ok === false) throw new Error(value.error || "The OS did not accept the request.");
        return value;
      }, done, status);
    } finally { busy = false; }
  }
  function review(command, args, title, explanation, confirm = false, done = null, summary = args) {
    if (busy || reviewing) return;
    if (!ClawApp.tool(app, command)) { notice.textContent = `This entry does not declare ${command}.`; return; }
    reviewing = true;
    const dialog = ui.node("dialog"); const form = ui.node("form");
    const check = ui.node("input", null, { type: "checkbox", required: "" });
    const acknowledgment = ui.node("label", "I understand the effect and confirm this exact request."); acknowledgment.append(check);
    const status = ui.node("p", "", { class: "notice", role: "status", "aria-live": "polite" });
    const cancel = ui.node("button", "Cancel", { type: "button" });
    const execute = ui.node("button", title, { type: "submit", class: "primary" });
    const actions = ui.node("div", null, { class: "toolbar" }); actions.append(cancel, execute);
    form.append(ui.node("p", explanation), detail(summary), acknowledgment, status, actions);
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (!check.checked || busy) return;
      cancel.disabled = true;
      await request(execute, command, confirm ? { ...args, confirm: true } : args, (value) => {
        evidence(title, value);
        notice.textContent = "Response received. Inspect current state before another request. No automatic retry.";
        if (done) done(value);
        dialog.close();
      }, status);
      cancel.disabled = false; check.checked = false;
      if (dialog.open) status.append(ui.node("span", " The effect may be unknown. Inspect current state before retrying."));
    };
    cancel.onclick = () => dialog.close();
    dialog.addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
    dialog.addEventListener("close", () => { reviewing = false; dialog.remove(); });
    dialog.append(ui.node("h2", title), form); document.body.append(dialog); dialog.showModal();
  }
  function statusCard(title, description, command = "status", onResult = null) {
    const card = section(title, description);
    const state = ui.node("div", "State has not been loaded.", { class: "stack muted" });
    button(card, `Inspect ${title.toLowerCase()}`, (control) => void request(control, command, {}, (value) => {
      ui.replace(state, [detail(value)]); if (onResult) onResult(value);
    }), "primary");
    card.append(state); return card;
  }

  function accessibility() {
    statusCard("Accessibility state", "Status uses sys.observe:accessibility; changes independently require ui.accessibility:control.");
    for (const [command, label, description] of [
      ["screen-reader", "Screen reader", "Change the OS screen-reader state for the authorized desktop session."],
      ["magnifier", "Magnifier", "Change the OS magnifier state. Selection alone does not affect the desktop."],
      ["invert", "Invert colors", "Change color inversion for the desktop session."],
    ]) {
      const card = section(label, description);
      const state = toggle(card, "Desired state (not current state)");
      button(card, `Review ${label.toLowerCase()}...`, () => review(command, { state: desired(state) }, `Set ${label.toLowerCase()}`, description));
    }
    const card = section("Color-vision filter", "Choose a closed, supported filter. Current state comes only from inspection.");
    const filter = choose(card, "Desired filter", [["", "Choose filter"], ["off", "Off"], ["greyscale", "Greyscale"], ["protanopia", "Protanopia"], ["deuteranopia", "Deuteranopia"], ["tritanopia", "Tritanopia"]]);
    button(card, "Review color filter...", () => review("filter", { filter: desired(filter) }, "Set color filter", "Apply the selected accessibility filter to the authorized desktop session."));
  }

  function audio() {
    let updateLists = () => {};
    statusCard("Audio devices and levels", "Output controls use device.audio:output; microphone controls use device.microphone:input. Defaults, routes and profiles separately use device.media-route:pipewire.", "status", (value) => updateLists(value));
    const outputs = section("Output", "Values below are desired changes, not live levels. Output can be amplified up to 150%; high volume can be uncomfortable.");
    const outputList = ui.node("div", null, { class: "scroll" }); outputs.append(outputList);
    const outputNode = field(outputs, "Exact output node ID", { type: "number", min: "1", max: "4096", step: "1" });
    const outputVolume = field(outputs, "Desired output volume (%)", { type: "number", min: "0", max: "150", step: "1", placeholder: "0-150" });
    const outputMute = toggle(outputs, "Desired output mute state (On means muted)");
    button(outputs, "Review output volume...", () => review("output-volume", { percent: integer(outputVolume, "Output percent", 0, 150) }, "Set output volume", "Change the current default output's volume; selecting a node does not redirect this volume command."));
    button(outputs, "Review output mute...", () => review("output-mute", { state: desired(outputMute) }, "Set output mute", "Change mute for the current default output."));
    button(outputs, "Use selected output as default...", () => review("output-default", { node_id: integer(outputNode, "Output node ID", 1, 4096) }, "Set default output", "Change the PipeWire default output. This can move subsequent audio to a different device."));
    const inputs = section("Microphone", "Input gain and mute affect the current default microphone, not an arbitrary node. No recording is started here.");
    const inputList = ui.node("div", null, { class: "scroll" }); inputs.append(inputList);
    const inputNode = field(inputs, "Exact input node ID", { type: "number", min: "1", max: "4096", step: "1" });
    const inputVolume = field(inputs, "Desired input gain (%)", { type: "number", min: "0", max: "100", step: "1", placeholder: "0-100" });
    const inputMute = toggle(inputs, "Desired microphone mute state (On means muted)");
    button(inputs, "Review microphone gain...", () => review("input-volume", { percent: integer(inputVolume, "Input percent", 0, 100) }, "Set microphone gain", "Change the current default microphone's gain."));
    button(inputs, "Review microphone mute...", () => review("input-mute", { state: desired(inputMute) }, "Set microphone mute", "Unmuting can make the microphone available to already-authorized consumers."));
    button(inputs, "Use selected input as default...", () => review("input-default", { node_id: integer(inputNode, "Input node ID", 1, 4096) }, "Set default input", "Change the PipeWire default input device."));
    updateLists = (value) => {
      for (const [target, key, input] of [[outputList, "outputs", outputNode], [inputList, "inputs", inputNode]]) list(target, value, [key], [
        { label: "Node", value: (item) => item.node_id ?? item.id ?? "Not reported" },
        { label: "Device", value: (item) => item.description || item.name || "Not reported" },
      ], (item) => { input.value = item.node_id ?? item.id ?? ""; evidence("Selected audio inventory record", item); });
    };
    const routes = advanced("Advanced audio routes and device profiles");
    const outputRoute = field(routes, "Output route index", { type: "number", min: "0", max: "4096", step: "1" });
    button(routes, "Review output route...", () => review("output-route", { node_id: integer(outputNode, "Output node ID", 1, 4096), route_index: integer(outputRoute, "Output route index", 0, 4096) }, "Set output route", "Use an exact route index from the inspected device evidence."));
    const inputRoute = field(routes, "Input route index", { type: "number", min: "0", max: "4096", step: "1" });
    button(routes, "Review input route...", () => review("input-route", { node_id: integer(inputNode, "Input node ID", 1, 4096), route_index: integer(inputRoute, "Input route index", 0, 4096) }, "Set input route", "Use an exact route index from the inspected device evidence."));
    const device = field(routes, "Device ID", { type: "number", min: "1", max: "4096", step: "1" });
    const profile = field(routes, "Profile index", { type: "number", min: "0", max: "4096", step: "1" });
    button(routes, "Review device profile...", () => review("profile", { device_id: integer(device, "Device ID", 1, 4096), profile_index: integer(profile, "Profile index", 0, 4096) }, "Set audio profile", "Changing a device profile may remove or reroute its audio nodes."));
  }

  function bluetooth() {
    let update = () => {};
    statusCard("Bluetooth inventory", "Status requires observation; scans, pairing and device changes separately require device.bluetooth:control. Nothing starts scanning on page load.", "status", (value) => update(value));
    const adapterCard = section("Adapter", "Choose an exact adapter MAC address, not an hci index. Editing fields is inert.");
    const adapters = ui.node("div", null, { class: "scroll" }); adapterCard.append(adapters);
    const adapter = field(adapterCard, "Adapter MAC address", { placeholder: "AA:BB:CC:DD:EE:FF", autocomplete: "off" });
    const state = toggle(adapterCard, "Desired adapter power");
    const seconds = field(adapterCard, "Explicit scan duration (seconds)", { type: "number", min: "1", max: "60", step: "1", value: "10" });
    function address(input, label) {
      const value = text(input, label);
      if (!/^(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$/.test(value)) throw new Error(`${label} must be a Bluetooth MAC address.`);
      return value;
    }
    button(adapterCard, "Review adapter power...", () => review("power", { adapter: address(adapter, "Adapter"), state: desired(state) }, "Set Bluetooth power", "Turning an adapter off disconnects its devices."));
    const deviceCard = section("Device", "Select an observed device or enter its exact MAC address. Pairing, connecting and trusting are separate operations.");
    const devices = ui.node("div", null, { class: "scroll" }); deviceCard.append(devices);
    const device = field(deviceCard, "Device MAC address", { placeholder: "11:22:33:44:55:66", autocomplete: "off" });
    const renderDevices = (value) => list(devices, value, ["devices"], [
      { label: "Device", value: (item) => item.address || item.device || "Not reported" },
      { label: "Name", value: (item) => item.name || item.alias || "Not reported" },
      { label: "Connected", value: (item) => item.connected === undefined ? "Not reported" : String(item.connected) },
    ], (item) => { device.value = item.address || item.device || ""; evidence("Selected Bluetooth record", item); });
    update = (value) => {
      list(adapters, value, ["adapters"], [
        { label: "Address", value: (item) => item.address || item.adapter || "Not reported" },
        { label: "Name", value: (item) => item.name || "Not reported" },
      ], (item) => { adapter.value = item.address || item.adapter || ""; evidence("Selected Bluetooth adapter", item); });
      renderDevices(value);
    };
    button(adapterCard, "Review device scan...", () => review("scan", { adapter: address(adapter, "Adapter"), seconds: integer(seconds, "Scan duration", 1, 60) }, "Scan Bluetooth devices", "This explicitly activates bounded device discovery on the selected adapter.", false, renderDevices));
    const pairing = section("Pairing session", "Pairing is owner-bound in the OS. Request status explicitly; no polling or automatic response is sent.");
    const pairingId = field(pairing, "Pairing ID", { placeholder: "32 hexadecimal characters from pairing evidence", autocomplete: "off" });
    button(deviceCard, "Begin pairing...", () => review("pair", { adapter: address(adapter, "Adapter"), device: address(device, "Device") }, "Begin Bluetooth pairing", "Start one pairing session for these exact devices.", false, (value) => { if (value && /^[0-9a-fA-F]{32}$/.test(value.pairing_id)) pairingId.value = value.pairing_id; }));
    for (const [command, label, message] of [
      ["connect", "Connect device", "Connect this device through the selected adapter."],
      ["disconnect", "Disconnect device", "Disconnect this device; input or audio may be interrupted."],
      ["trust", "Trust device", "Change the OS device trust state; pairing alone does not imply trust."],
      ["untrust", "Remove trust", "Remove this device's trusted state."],
      ["forget", "Forget device", "Forget the saved device pairing. Re-pairing may be needed."],
    ]) button(deviceCard, `${label}...`, () => review(command, { adapter: address(adapter, "Adapter"), device: address(device, "Device") }, label, message));
    button(pairing, "Inspect pairing status", (control) => { const args = { pairing_id: token(pairingId, "Pairing ID") }; void request(control, "pair-status", args, (value) => evidence("Pairing status", value)); });
    const response = field(pairing, "Pairing response (only when prompted by the OS)", { type: "password", maxlength: "32", autocomplete: "off" });
    button(pairing, "Review pairing response...", () => {
      const args = { pairing_id: token(pairingId, "Pairing ID"), response: text(response, "pairing response", 32) };
      review("pair-respond", args, "Respond to pairing challenge", "Supply the response for this pairing session only. The client passes it through the service's stdin-only response path, not broker argv.", false, () => { response.value = ""; }, { pairing_id: args.pairing_id, response: "Hidden pairing response" });
    });
    button(pairing, "Cancel pairing...", () => review("pair-cancel", { pairing_id: token(pairingId, "Pairing ID") }, "Cancel pairing session", "Ask the OS to cancel this exact pairing session."));
  }

  function camera() {
    let update = () => {};
    statusCard("Camera inventory", "Discovery uses sys.observe:camera. Capture separately activates a camera and writes one new image under exact destination authority.", "status", (value) => update(value));
    const capture = section("Still-image capture", "There is no live preview or automatic camera activation. The OS revalidates the selected node serial and never overwrites an existing destination.");
    const cameras = ui.node("div", null, { class: "scroll" }); capture.append(cameras);
    const node = field(capture, "Node ID", { type: "number", min: "1", max: "4294967295", step: "1" });
    const serial = field(capture, "Expected node serial", { type: "number", min: "1", step: "1", placeholder: "Exact serial from current inventory" });
    update = (value) => list(cameras, value, ["cameras"], [
      { label: "Camera", value: (item) => item.name || item.description || "Not reported" },
      { label: "Node", key: "node_id" }, { label: "Serial", value: (item) => item.serial ?? item.expected_serial ?? "Not reported" },
    ], (item) => { node.value = item.node_id ?? ""; serial.value = item.serial ?? item.expected_serial ?? ""; evidence("Selected camera inventory record", item); });
    const destination = field(capture, "New canonical destination path", { placeholder: "/home/user/Pictures/capture.png", autocomplete: "off" });
    const format = choose(capture, "Image format", [["png", "PNG"], ["jpeg", "JPEG"]], "png");
    const width = field(capture, "Width", { type: "number", min: "16", max: "7680", step: "1", value: "1280" });
    const height = field(capture, "Height", { type: "number", min: "16", max: "4320", step: "1", value: "720" });
    button(capture, "Review camera capture...", () => review("capture", {
      node_id: integer(node, "Camera node ID", 1, 4294967295), expected_serial: integer(serial, "Expected serial", 1, Number.MAX_SAFE_INTEGER),
      destination: path(destination, "Destination"), format: format.value, width: integer(width, "Width", 16, 7680), height: integer(height, "Height", 16, 4320),
    }, "Capture one image", "This activates the exact camera and writes an image. It needs device.camera:capture and fs.write for the exact new destination."), "primary");
  }

  function displays() {
    let update = () => {};
    statusCard("Display inventory", "Inspection uses sys.observe:display. Every change separately requires device.display:manage. No mode or brightness changes occur on selection.", "status", (value) => update(value));
    const mode = section("Output and mode", "Desired values are not current configuration. Screen changes can make the display unavailable; no automatic recovery timer is promised.");
    const outputs = ui.node("div", null, { class: "scroll" }); mode.append(outputs);
    const output = field(mode, "Exact output name", { placeholder: "HDMI-A-1", maxlength: "64", autocomplete: "off" });
    function outputName(input = output, maximum = 64) {
      const value = text(input, "output name", maximum);
      if (!/^[A-Za-z0-9][A-Za-z0-9_.:-]*$/.test(value)) throw new Error("Use an exact output or backlight name from inspection.");
      return value;
    }
    update = (value) => list(outputs, value, ["outputs"], [
      { label: "Output", value: (item) => item.output || item.name || "Not reported" },
      { label: "Enabled", value: (item) => item.enabled === undefined ? "Not reported" : String(item.enabled) },
    ], (item) => { output.value = item.output || item.name || ""; evidence("Selected output record", item); });
    const width = field(mode, "Desired width", { type: "number", min: "1", max: "16384", step: "1" });
    const height = field(mode, "Desired height", { type: "number", min: "1", max: "16384", step: "1" });
    const refresh = field(mode, "Desired refresh rate in Hz (optional)", { type: "number", min: "1", max: "1000", step: "any" });
    const scale = field(mode, "Desired scale (optional for mode)", { type: "number", min: "0.5", max: "4", step: "any", placeholder: "0.5-4" });
    const transform = choose(mode, "Transform (optional)", [["", "Leave unspecified"], "normal", "rotate90", "rotate180", "rotate270", "flipped", "flipped90", "flipped180", "flipped270"]);
    const adaptive = choose(mode, "Adaptive sync (optional)", [["", "Leave unspecified"], ["true", "Enabled"], ["automatic", "Automatic"], ["false", "Disabled"]]);
    button(mode, "Review display mode...", () => {
      const args = { output: outputName(), width: integer(width, "Width", 1, 16384), height: integer(height, "Height", 1, 16384) };
      if (refresh.value !== "") args.refresh = number(refresh, "Refresh rate", 1, 1000);
      if (scale.value !== "") args.scale = number(scale, "Scale", 0.5, 4);
      if (transform.value) args.transform = transform.value;
      if (adaptive.value) args.adaptive_sync = adaptive.value;
      review("mode", args, "Set display mode", "Apply only the supplied mode values. The OS validates device and mode availability; unsupported modes can be refused.");
    }, "primary");
    button(mode, "Review scale only...", () => review("scale", { output: outputName(), scale: number(scale, "Scale", 0.5, 4) }, "Set output scale", "Change only this output's scale."));
    for (const [command, label] of [["enable", "Enable output"], ["disable", "Disable output"]]) button(mode, `${label}...`, () => review(command, { output: outputName() }, label, "This can change which screens are usable. The OS retains its display safety checks."));
    const layout = advanced("Position, mirroring, backlight and recorded layouts");
    const x = field(layout, "Desired X position", { type: "number", min: "-32768", max: "32768", step: "1" });
    const y = field(layout, "Desired Y position", { type: "number", min: "-32768", max: "32768", step: "1" });
    button(layout, "Review output position...", () => review("position", { output: outputName(), x: integer(x, "X", -32768, 32768), y: integer(y, "Y", -32768, 32768) }, "Position output", "Move the selected output in desktop coordinates."));
    const mirror = field(layout, "Mirror source output", { placeholder: "Exact source output", maxlength: "64" });
    button(layout, "Review mirroring...", () => review("mirror", { output: outputName(), source_output: outputName(mirror) }, "Mirror output", "Mirror the selected source onto the target output."));
    const backlight = field(layout, "Exact backlight name", { maxlength: "128", placeholder: "Name from inspected evidence" });
    const brightness = field(layout, "Desired brightness (%)", { type: "number", min: "1", max: "100", step: "1" });
    button(layout, "Review brightness...", () => review("brightness", { backlight: outputName(backlight, 128), percent: integer(brightness, "Brightness", 1, 100) }, "Set backlight brightness", "Change the selected kernel backlight only."));
    const source = field(layout, "Canonical layout source file", { placeholder: "/home/user/layout.json", autocomplete: "off" });
    button(layout, "Review saved layout...", () => review("apply-layout", { source: path(source, "Layout source") }, "Apply saved layout", "Needs exact layout-file read permission in addition to display management. The whole layout may change.", true));
    const backup = field(layout, "Owner-bound backup token", { placeholder: "32 hexadecimal characters", autocomplete: "off" });
    button(layout, "Review layout restore...", () => review("restore", { backup_token: token(backup) }, "Restore display layout", "Restore only if the OS accepts this owner-bound backup token.", true));
  }

  function desktop() {
    let update = () => {};
    statusCard("Desktop windows", "Listing uses sys.observe:desktop. Window control is separate, and restart also needs desktop.launch for the exact AppID. These are OS window operations, not calls to another App.", "list", (value) => update(value));
    const controls = section("Selected window", "Selection does not focus or close a window. Unsaved work may be lost by close or restart.");
    const windows = ui.node("div", null, { class: "scroll" }); controls.append(windows);
    const identifier = field(controls, "Exact window identifier returned by list", { maxlength: "512", autocomplete: "off" });
    const appId = field(controls, "Exact desktop AppID (restart only)", { placeholder: "AppID returned by list", maxlength: "255", autocomplete: "off" });
    update = (value) => list(windows, value, ["windows"], [
      { label: "Title", value: (item) => item.title || "Not reported" }, { label: "Window", key: "identifier" }, { label: "AppID", key: "app_id" },
    ], (item) => { identifier.value = item.identifier || ""; appId.value = item.app_id || ""; evidence("Selected window record", item); });
    function windowId() {
      const value = text(identifier, "window identifier", 512);
      if (value.startsWith("-")) throw new Error("Use an identifier returned by the window list.");
      return value;
    }
    button(controls, "Focus window...", () => review("focus", { identifier: windowId() }, "Focus window", "Request focus for this exact compositor window."));
    button(controls, "Close window...", () => review("close", { identifier: windowId() }, "Close window", "Request closure of this exact window. Save work first; closing is not guaranteed to be reversible."));
    button(controls, "Restart application...", () => {
      const value = text(appId, "desktop AppID", 255);
      if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$/.test(value)) throw new Error("Use the exact desktop AppID returned by list.");
      review("restart", { identifier: windowId(), app_id: value }, "Restart application", "The OS closes the identified window and relaunches the exact matching AppID. This is not a generic launch route.");
    });
  }

  function location() {
    const card = section("Explicit location request", "Both operations use this identity's device.location grant. No location request runs on page load. GeoClue access and consent remain with the OS.");
    const accuracy = choose(card, "Requested accuracy (not a current fix)", ["country", "city", "neighborhood", "street", "exact"], "city");
    button(card, "Review location request...", () => review("locate", { accuracy: accuracy.value }, "Request location", "This requests a location fix at the selected accuracy and may disclose sensitive location data."));
    button(card, "Review timezone suggestion...", () => review("timezone", { accuracy: accuracy.value }, "Suggest timezone", "The OS may obtain location to produce an offline timezone suggestion. It does not change the system timezone."));
  }

  function network() {
    statusCard("Network state", "Observation is separate from net.manage:wifi, net.manage:vpn and net.manage:airplane. Credentials are stored references; this page never accepts a Wi-Fi password.");
    const wifi = section("Wi-Fi networks", "Loading networks is an explicit scan/read. Selecting a network does not connect to it.");
    const networks = ui.node("div", null, { class: "scroll" }); wifi.append(networks);
    const ssid = field(wifi, "Exact SSID", { autocomplete: "off", placeholder: "Network name" });
    const credential = field(wifi, "Stored credential reference (optional for open networks)", { autocomplete: "off", placeholder: "Exact OS credential name, not a password" });
    button(wifi, "Load nearby Wi-Fi networks", (control) => void request(control, "wifi-list", {}, (value) => {
      evidence("Nearby Wi-Fi evidence", value);
      list(networks, value, ["networks", "wifi"], [
        { label: "SSID", key: "ssid" }, { label: "Signal", value: (item) => item.signal ?? "Not reported" },
        { label: "Security", value: (item) => item.security || "Not reported" },
      ], (item) => { ssid.value = item.ssid || ""; evidence("Selected Wi-Fi record", item); });
    }), "primary");
    button(wifi, "Review Wi-Fi connection...", () => {
      const args = { ssid: text(ssid, "SSID") };
      if (credential.value.trim()) args.credential = text(credential, "stored credential reference");
      review("wifi-connect", args, "Connect to Wi-Fi", "The OS loads the optional referenced secret under exact secret.read authority. This may replace the active connection; no plaintext password is sent.");
    });
    const saved = section("Saved connections and disconnect", "Forgetting a profile and disconnecting a device are different operations with different targets.");
    const connections = ui.node("div", null, { class: "scroll" }); saved.append(connections);
    const connection = field(saved, "Exact saved connection ID or name", { autocomplete: "off" });
    const device = field(saved, "Exact Wi-Fi device to disconnect", { placeholder: "wlan0", autocomplete: "off" });
    button(saved, "Load saved connections", (control) => void request(control, "connection-list", {}, (value) => {
      evidence("Saved network connections", value);
      list(connections, value, ["connections"], [
        { label: "Name", value: (item) => item.name || item.id || "Not reported" }, { label: "UUID", key: "uuid" }, { label: "Type", key: "type" },
      ], (item) => { connection.value = item.uuid || item.id || item.name || ""; evidence("Selected connection record", item); });
    }));
    button(saved, "Disconnect Wi-Fi device...", () => review("wifi-disconnect", { device: text(device, "Wi-Fi device") }, "Disconnect Wi-Fi", "This can interrupt the network session. The target is a device, not an SSID."));
    button(saved, "Forget saved Wi-Fi profile...", () => review("wifi-forget", { connection: text(connection, "saved connection") }, "Forget Wi-Fi profile", "Delete this exact saved connection profile. Credentials or settings may need to be supplied again."));
    const vpn = section("VPN profiles", "VPN lifecycle uses net.manage:vpn, not Wi-Fi authority. This UI cannot create or edit profiles.");
    const profiles = ui.node("div", null, { class: "scroll" }); vpn.append(profiles);
    const profile = field(vpn, "Exact VPN profile ID or name", { autocomplete: "off" });
    button(vpn, "Load VPN profiles", (control) => void request(control, "vpn-list", {}, (value) => {
      evidence("VPN profiles", value);
      list(profiles, value, ["profiles", "vpns", "connections"], [
        { label: "Profile", value: (item) => item.name || item.id || "Not reported" }, { label: "UUID", key: "uuid" }, { label: "State", key: "state" },
      ], (item) => { profile.value = item.uuid || item.id || item.name || ""; evidence("Selected VPN profile", item); });
    }));
    button(vpn, "Activate VPN...", () => review("vpn-up", { profile: text(profile, "VPN profile") }, "Activate VPN", "Activate only this saved VPN/WireGuard profile through the OS."));
    button(vpn, "Deactivate VPN...", () => review("vpn-down", { profile: text(profile, "VPN profile") }, "Deactivate VPN", "This can remove protected routes and interrupt active connections."));
    const radios = advanced("Global Wi-Fi and airplane radio controls");
    const wifiState = toggle(radios, "Desired Wi-Fi radio state");
    button(radios, "Review Wi-Fi radio...", () => review("wifi-toggle", { state: desired(wifiState) }, "Set Wi-Fi radio", "Change the global Wi-Fi radio state; this can disconnect networks."));
    const airplane = toggle(radios, "Desired airplane mode");
    button(radios, "Review airplane mode...", () => review("airplane", { state: desired(airplane) }, "Set airplane mode", "Change all NetworkManager radio state under separate airplane authority."));
  }

  function power() {
    statusCard("Power status", "UPower/logind observation is separate from critical machine-wide sys.power authority. No sleep or power action is sent at startup.");
    const sleep = section("Sleep and hibernation", "Save work before requesting a system-wide transition. The OS checks support and authorization; a lost connection is not proof of completion.");
    for (const [command, label] of [["suspend", "Suspend"], ["hibernate", "Hibernate"]]) button(sleep, `${label}...`, () => review(command, {}, label, "This affects the whole machine and may disconnect this UI. Do not retry an uncertain request automatically.", true));
    const critical = section("Restart or shut down", "These actions interrupt every App and session. Explicit confirmation is required for each request.");
    for (const [command, label] of [["reboot", "Reboot system"], ["poweroff", "Power off system"]]) button(critical, `${label}...`, () => review(command, {}, label, "Save all work. This is a machine-wide critical action, not an App lifecycle operation.", true), "danger");
    const other = advanced("Advanced sleep transitions");
    for (const [command, label] of [["hybrid-sleep", "Hybrid sleep"], ["suspend-then-hibernate", "Suspend then hibernate"]]) button(other, `${label}...`, () => review(command, {}, label, "Request this logind transition only if the OS supports it. Every request needs fresh explicit confirmation.", true));
  }

  function printers() {
    let update = () => {};
    statusCard("Printer discovery", "Discovery uses sys.observe:printing. Queue reads, printing and job cancellation have separate device.printer scopes.", "status", (value) => update(value));
    const target = section("Printer and queue", "Selecting a printer does not inspect its capabilities, load its queue or submit a document.");
    const inventory = ui.node("div", null, { class: "scroll" }); target.append(inventory);
    const printer = field(target, "Exact printer name", { placeholder: "office", autocomplete: "off", maxlength: "127" });
    function printerName(required = true) {
      if (!required && !printer.value.trim()) return null;
      const value = text(printer, "printer name", 127);
      if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,126}$/.test(value)) throw new Error("Use an exact printer name returned by discovery.");
      return value;
    }
    update = (value) => list(inventory, value, ["printers"], [
      { label: "Printer", value: (item) => item.name || item.printer || "Not reported" }, { label: "State", key: "state" },
    ], (item) => { printer.value = item.name || item.printer || ""; evidence("Selected printer record", item); });
    button(target, "Inspect printer capabilities", (control) => { const args = { printer: printerName() }; void request(control, "capabilities", args, (value) => evidence(`Printer capabilities: ${args.printer}`, value)); });
    const jobs = ui.node("div", null, { class: "scroll" }); target.append(jobs);
    const job = field(target, "Exact job ID to cancel", { placeholder: "office-123", autocomplete: "off" });
    button(target, "Load queue (blank printer means all)", (control) => {
      const name = printerName(false); const args = name ? { printer: name } : {};
      void request(control, "jobs", args, (value) => {
        evidence("Print queue evidence", value);
        list(jobs, value, ["jobs"], [
          { label: "Job", value: (item) => item.job_id || item.id || "Not reported" }, { label: "Title", key: "title" }, { label: "State", key: "state" },
        ], (item) => { job.value = item.job_id || item.id || ""; evidence("Selected print job", item); });
      });
    });
    button(target, "Cancel exact job...", () => {
      const id = text(job, "print job ID");
      if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,126}-[0-9]+$/.test(id)) throw new Error("Use the complete printer-number job ID.");
      review("cancel", { job_id: id }, "Cancel print job", "The OS validates job ownership. Cancellation does not undo pages already printed.", true);
    });
    const print = section("Print a document", "Source bytes remain in the exact OS file. Printing requires device.printer:print and fs.read for that source, not a browser upload.");
    const source = field(print, "Canonical source file", { placeholder: "/home/user/Documents/report.pdf", autocomplete: "off" });
    const copies = field(print, "Copies", { type: "number", min: "1", max: "100", step: "1", value: "1" });
    const sides = choose(print, "Sides", [["", "Printer default"], ["one-sided", "One-sided"], ["two-sided-long-edge", "Two-sided, long edge"], ["two-sided-short-edge", "Two-sided, short edge"]]);
    const title = field(print, "Job title (optional)", { maxlength: "128" });
    const media = field(print, "Media option (optional)", { placeholder: "Exact supported media name", maxlength: "128" });
    button(print, "Review print submission...", () => {
      const args = { printer: printerName(), source: path(source, "Print source"), copies: integer(copies, "Copies", 1, 100) };
      if (sides.value) args.sides = sides.value;
      if (title.value.trim()) args.title = text(title, "print title", 128);
      if (media.value.trim()) {
        args.media = text(media, "media option", 128);
        if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(args.media)) throw new Error("Media must be an exact supported option name.");
      }
      review("print", args, "Submit print job", "This sends a real document to the selected printer. A returned job ID is queue evidence, not proof that every page printed.");
    }, "primary");
  }

  function users() {
    let update = () => {};
    statusCard("Local identities", "Inspection uses sys.observe:identities. Changes use critical sys.identity:manage. Password changes load an exact credential reference only; no plaintext password is accepted.", "status", (value) => update(value));
    const selected = section("Selected account", "Account and group selections are inert. Deleting a user retains its home directory under the existing service contract.");
    const accounts = ui.node("div", null, { class: "scroll" }); selected.append(accounts);
    const user = field(selected, "Exact user name", { maxlength: "32", autocomplete: "off" });
    function name(input, label) {
      const value = text(input, label, 32);
      if (!/^[a-z_][a-z0-9_-]{0,31}$/.test(value)) throw new Error(`${label} must be a valid lowercase local identity name.`);
      return value;
    }
    update = (value) => list(accounts, value, ["users"], [
      { label: "User", value: (item) => item.user || item.name || "Not reported" },
      { label: "Full name", value: (item) => item.full_name || "Not reported" }, { label: "Shell", key: "shell" },
    ], (item) => { user.value = item.user || item.name || ""; evidence("Selected local account record", item); });
    for (const [command, label, message, confirm] of [
      ["lock-user", "Lock account", "Lock this local account. This may prevent future authentication; it is not a promise to end existing sessions.", false],
      ["unlock-user", "Unlock account", "Unlock this exact local account through the OS.", false],
      ["delete-user", "Delete account", "Delete this exact account but retain its home directory. No data migration or rollback is promised.", true],
    ]) button(selected, `${label}...`, () => review(command, { user: name(user, "User name") }, label, message, confirm));
    const password = field(selected, "Password credential reference (namespace/name)", { placeholder: "users/alex-password", autocomplete: "off" });
    button(selected, "Review password reference...", () => {
      const credential = text(password, "password credential reference", 511);
      if (!/^(?!-)[A-Za-z0-9_.:-]{1,255}\/(?!-)[A-Za-z0-9_.:-]{1,255}$/.test(credential)) throw new Error("Use a stored namespace/name credential reference, never a plaintext password.");
      review("set-password", { user: name(user, "User name"), credential }, "Change account password", "The OS loads this referenced credential under exact secret.read authority. The App never receives or displays its plaintext.");
    });
    const shell = field(selected, "Desired canonical shell path", { placeholder: "/bin/bash", autocomplete: "off", maxlength: "255" });
    button(selected, "Review account shell...", () => review("set-shell", { user: name(user, "User name"), shell: path(shell, "Shell path") }, "Set account shell", "The OS validates the canonical shell against its allowlist."));
    const create = section("Create a local account", "New-account values are explicit and are not copied from the selected account. Defaults and admission remain with the OS.");
    const newUser = field(create, "New user name", { maxlength: "32", autocomplete: "off" });
    const fullName = field(create, "Full name (optional)", { maxlength: "128" });
    const groups = field(create, "Initial groups (optional, comma-separated)", { placeholder: "Exact existing group names" });
    const newShell = field(create, "Canonical shell path (optional)", { maxlength: "255", placeholder: "/bin/bash" });
    button(create, "Review account creation...", () => {
      const args = { user: name(newUser, "New user name") };
      if (fullName.value.trim()) {
        args.full_name = text(fullName, "full name", 128);
        if (args.full_name.includes(":")) throw new Error("Full name cannot contain a colon.");
      }
      if (groups.value.trim()) {
        const values = groups.value.split(",").map((value) => value.trim());
        if (values.length > 64 || new Set(values).size !== values.length || values.some((value) => !/^[a-z_][a-z0-9_-]{0,31}$/.test(value))) throw new Error("Use 1-64 distinct, non-empty local group names.");
        args.groups = values.join(",");
      }
      if (newShell.value.trim()) args.shell = path(newShell, "Shell path");
      review("create-user", args, "Create local account", "Create this exact account. This does not set a password or grant App permissions.");
    }, "primary");
    const groupCard = advanced("Group membership, group creation and recorded identity restore");
    const group = field(groupCard, "Exact group name", { maxlength: "32", autocomplete: "off" });
    for (const [command, label, includeUser, confirm] of [
      ["create-group", "Create group", false, false], ["delete-group", "Delete group", false, true],
      ["add-to-group", "Add selected account to group", true, false], ["remove-from-group", "Remove selected account from group", true, false],
    ]) button(groupCard, `${label}...`, () => {
      const args = { group: name(group, "Group name") }; if (includeUser) args.user = name(user, "User name");
      review(command, args, label, "This changes local identity/group state and can change future access. The OS retains identity safety checks.", confirm);
    });
    const backup = field(groupCard, "Owner-bound identity backup token", { placeholder: "32 hexadecimal characters", autocomplete: "off" });
    button(groupCard, "Review identity restore...", () => review("restore", { backup_token: token(backup) }, "Restore identity change", "Restore only the recorded owner-bound mutation accepted by the OS. No general account-state rollback is implied.", true));
  }

  function nativeSettings() {
    const pages = section("Native settings pages", "This identity discovers and opens the fixed native Settings target. It does not inherit the eleven management Apps' device or account grants.");
    const pageList = ui.node("div", null, { class: "scroll" }); pages.append(pageList);
    ui.replace(pageList, [ui.node("p", "Page catalog has not been loaded.", { class: "empty" })]);
    let selectedPage = null;
    const pageSelection = ui.node("p", "No page selected.", { class: "muted" }); pages.append(pageSelection);
    function renderPages(value, key) {
      selectedPage = null; pageSelection.textContent = "No page selected.";
      if (!value || !Array.isArray(value[key])) throw new Error("The native service did not return the expected page catalog.");
      ui.table(pageList, value[key], [
        { label: "Page", key: "label" }, { label: "Description", key: "hint" },
      ], { label: "Select", run: (item) => { selectedPage = item.id; pageSelection.textContent = `${item.label} (${item.id}): ${item.hint}`; } });
    }
    button(pages, "Load native page catalog", (control) => void request(control, "list_pages", {}, (value) => renderPages(value, "pages")), "primary");
    const query = field(pages, "Search page names and descriptions", { placeholder: "network, appearance, applications..." });
    const limit = field(pages, "Maximum search matches", { type: "number", min: "1", max: "20", step: "1", value: "5" });
    button(pages, "Search pages", (control) => void request(control, "search", { query: text(query, "page query"), limit: integer(limit, "Search limit", 1, 20) }, (value) => renderPages(value, "hits")));
    button(pages, "Open selected native page...", () => {
      if (typeof selectedPage !== "string" || !selectedPage) throw new Error("Select a page returned by the native catalog first.");
      review("open", { page: selectedPage }, "Open native Settings page", "Activate only the fixed OS Settings target. Native page and launch admission can still fail; no device operation is performed by selection.");
    });
    button(pages, "Open native Settings...", () => review("open", {}, "Open native Settings", "Explicitly launch the fixed native Settings target under proc.spawn:cosmic-settings."));

    const catalog = section("Verified installed Apps", "Permission management uses sys.permissions:manage only. Inspecting another App's declarations never invokes that App or borrows its grants.");
    const catalogEvidence = ui.node("div", null, { class: "stack" }); catalog.append(catalogEvidence);
    const selected = choose(catalog, "Verified App to inspect", [["", "Load and select a verified App"]]);
    let verified = new Set();
    let detailsEpoch = 0;
    let currentDetails = null;
    const permissions = section("Declared and effective permission state", "Only a fresh OS query can establish enablement or live daemon grants. Restoration requests remain pending for human OS review; an acknowledgement never means enabled.");
    const permissionList = ui.node("div", "No App permission state loaded.", { class: "stack" }); permissions.append(permissionList);
    const reason = field(permissions, "Reason for a restoration request (not an approval)", { rows: "3", placeholder: "Why this declared permission is needed" }, "textarea");
    function invalidate() {
      detailsEpoch++; currentDetails = null;
      ui.replace(permissionList, [ui.node("p", "Inspect the selected App again before making permission changes.", { class: "muted" })]);
    }
    selected.onchange = invalidate;
    button(catalog, "Load verified App catalog", (control) => void request(control, "permissions_list", {}, (value) => {
      if (!value || !Array.isArray(value.apps) || !Array.isArray(value.quarantined)) throw new Error("Invalid verified App catalog. Update the OS permission service and refresh.");
      verified = new Set(value.apps.map((item) => item.app_id).filter((id) => typeof id === "string"));
      ui.replace(selected, [ui.node("option", "Select a verified App", { value: "" }), ...Array.from(verified).map((id) => ui.node("option", id, { value: id }))]);
      invalidate();
      ui.replace(catalogEvidence, [ui.node("p", `${verified.size} verified Apps returned.${value.truncated ? " The catalog is truncated." : ""}`),
        ui.node("h3", "Quarantine and verification errors"), detail(value.quarantined)]);
    }), "primary");
    button(catalog, "Inspect selected App permissions", (control) => {
      const id = selected.value;
      if (!verified.has(id)) throw new Error("Select an App from the verified catalog.");
      const epoch = detailsEpoch;
      void request(control, "permissions_show", { app_id: id }, (value) => {
        if (epoch !== detailsEpoch || selected.value !== id) return;
        if (!value || value.app_id !== id || !Array.isArray(value.permissions)) throw new Error("Permission response does not match the selected App. Refresh; no policy state is assumed.");
        currentDetails = value;
        renderPermissions(value);
      });
    });
    function renderPermissions(value) {
      const cards = [ui.node("h3", `${value.app_id} (${value.trust || "trust not reported"})`, { class: "prose" }), ui.node("p", value.semantics || "State is supplied by the OS permission service.")];
      for (const permission of value.permissions) {
        const card = ui.node("section", null, { class: "card stack" });
        card.append(ui.node("h3", permission.permission_id || "Unidentified declaration", { class: "prose" }), detail(permission.capability || permission.declared));
        const enabled = typeof permission.enabled === "boolean" ? permission.enabled ? "Yes" : "No" : "Unknown";
        const granted = typeof permission.live_granted === "boolean" ? permission.live_granted ? "Yes" : "No" : "Unknown";
        card.append(ui.node("p", `Owner/App policy enabled: ${enabled}. Current daemon grant: ${granted}.`, { class: "prose" }));
        const declaration = ui.node("details"); declaration.append(ui.node("summary", "Verified declaration"), detail(permission.declared)); card.append(declaration);
        if (permission.manageable === true && typeof permission.enabled === "boolean" && typeof permission.permission_id === "string") {
          button(card, permission.enabled ? "Revoke permission..." : "Request restoration...", () => {
            if (currentDetails !== value || selected.value !== value.app_id) throw new Error("Permission state is stale. Inspect this App again.");
            const args = { app_id: value.app_id, permission_id: permission.permission_id };
            const command = permission.enabled ? "permissions_revoke" : "permissions_request";
            if (!permission.enabled) args.reason = text(reason, "restoration reason");
            review(command, args, permission.enabled ? "Revoke declared permission" : "Request permission restoration",
              permission.enabled ? "Disable this one brokered permission and invalidate this owner's target App grants. Restart/retry the affected App afterward. Already-authorized effects are not rolled back." :
                "This creates a pending request, not approval or a live grant. A human must review it in the OS approval gate or cos review. This UI cannot approve, choose a grant duration or expand manifest ceilings.",
              false, () => {
                invalidate();
                notice.textContent = permission.enabled ? "Revocation request returned. Inspect this App again to see actual policy state; restart/retry the affected App." : "Restoration request returned pending. Complete human OS review, then inspect this App again. No enabled state has been assumed.";
              });
          });
        } else card.append(ui.node("p", permission.limitation || "This declaration is not changeable here. Direct resources, argument-bound scopes and unknown state remain read-only.", { class: "muted" }));
        cards.push(card);
      }
      if (!value.permissions.length) cards.push(ui.node("p", "This verified App returned no permission declarations.", { class: "empty" }));
      cards.push(ui.node("h3", "Pending OS reviews"), detail(value.pending), ui.node("h3", "Recent decisions (read-only; not enablement proof)"), detail(value.recent));
      ui.replace(permissionList, cards);
    }
  }

  switch (app.id) {
    case "accessibility-manager": accessibility(); break;
    case "audio-manager": audio(); break;
    case "bluetooth-manager": bluetooth(); break;
    case "camera-manager": camera(); break;
    case "display-manager": displays(); break;
    case "desktop-manager": desktop(); break;
    case "location-manager": location(); break;
    case "network-manager": network(); break;
    case "power-manager": power(); break;
    case "printer-manager": printers(); break;
    case "user-manager": users(); break;
    case "cosmic-settings": nativeSettings(); break;
    default: root.append(ui.node("p", "This identity has no supported Settings interface. No other entry's tools are exposed.", { class: "empty" }));
  }
}).catch((error) => {
  document.getElementById("notice").textContent = `Settings UI unavailable: ${error.message}`;
});
