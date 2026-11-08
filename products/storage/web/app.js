ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  const defaults = () => ({ device: document.querySelector("#device").value });
  const output = (value) => ui.output(document.querySelector("#result"), value);
  document.querySelector("#refresh").onclick = (event) => void ui.run(event.target, () => ClawApp.call("status"), (value) => {
    const devices = ui.rows(value, ["devices", "blockdevices", "items"]);
    if (!devices.length) { ui.output(document.querySelector("#devices"), value); return; }
    ui.table(document.querySelector("#devices"), devices, [
      { label: "Device", value: (item) => item.device || item.path || item.name },
      { label: "Model", key: "model" }, { label: "Size", key: "size" }, { label: "Mount", value: (item) => item.mountpoint || item.mount },
    ], { label: "Select", run: (item) => { document.querySelector("#device").value = item.device || item.path || item.name; output(item); } });
  }, document.querySelector("#notice"));
  ui.actions(document.querySelector("#actions"), app, ["health", "check", "mount", "unmount", "eject"], output, defaults);
  ui.allTools(document.querySelector("#more"), app, output, defaults);
});
