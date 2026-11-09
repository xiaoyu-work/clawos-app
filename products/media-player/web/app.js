ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const $ = (selector) => document.querySelector(selector);
  const has = (command) => Boolean(ClawApp.tool(app, command));
  let busy = false;
  let observed = false;
  ui.showApp(app);

  function call(command) {
    const tool = ClawApp.tool(app, command);
    if (!tool) throw new Error(`This entry does not declare ${command}.`);
    return ClawApp.call(tool.name, {});
  }
  function checked(value) {
    ui.output($("#raw"), value);
    if (value && value.error) throw new Error(String(value.error));
    return value;
  }
  function update() {
    $("#refresh").disabled = busy || !has("status");
    for (const button of $("#controls").querySelectorAll("button")) button.disabled = busy || !observed;
  }
  function stale() {
    observed = false;
    $("#state").textContent = "Not currently confirmed";
    $("#observation").textContent = "Last observation - stale or unavailable";
  }
  function duration(micros) {
    if (typeof micros !== "number" || !Number.isFinite(micros) || micros < 0) return "Not reported";
    const seconds = Math.floor(micros / 1000000);
    const hours = Math.floor(seconds / 3600);
    return hours ? `${hours}:${String(Math.floor(seconds / 60) % 60).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}` :
      `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  }
  function render(value) {
    if (!value || !["Playing", "Paused", "Stopped"].includes(value.status)) throw new Error("The service returned no recognized live playback state.");
    $("#state").textContent = value.status;
    $("#observation").textContent = "Latest native playback observation";
    $("#title").textContent = value.title || (value.url ? "Untitled media" : "No current media reported");
    $("#artist").textContent = Array.isArray(value.artist) ? value.artist.join(", ") : "";
    $("#album").textContent = value.album ? `Album: ${value.album}` : "";
    $("#url").textContent = value.url || "Not reported";
    $("#duration").textContent = duration(value.length_micros);
    $("#observed-at").textContent = `Observed locally at ${new Date().toLocaleTimeString()}. This is a snapshot, not a continuously updated playhead.`;
    $("#current-item").textContent = value.title || value.url ?
      `Current item only: ${value.title || value.url}${Array.isArray(value.artist) && value.artist.length ? ` - ${value.artist.join(", ")}` : ""}` :
      "No current item reported. The playlist itself is not exposed.";
    observed = true;
  }
  async function perform(action, renderResult) {
    if (busy) return;
    busy = true;
    update();
    await ui.run(null, action, renderResult, $("#notice"));
    busy = false;
    update();
  }
  function refresh() {
    void perform(async () => {
      stale();
      return checked(await call("status"));
    }, render);
  }
  for (const [command, label] of [
    ["previous", "Previous"], ["play", "Play"], ["pause", "Pause"],
    ["toggle", "Play / pause"], ["next", "Next"], ["stop", "Stop"],
  ]) {
    if (!has(command)) continue;
    const button = ui.node("button", label, { type: "button" });
    button.onclick = () => {
      if (busy || !observed) return;
      void perform(async () => {
        stale();
        $("#outcome").textContent = `${label} requested once. Playback remains unconfirmed until the service reports it.`;
        const value = checked(await call(command));
        if (value?.ok !== true) throw new Error("The command was not confirmed. Refresh state before requesting another control.");
        $("#outcome").textContent = `${label} request acknowledged by the service. Reading native state; no optimistic playback state is invented.`;
        return checked(await call("status"));
      }, render);
    };
    $("#controls").append(button);
  }
  $("#refresh").onclick = refresh;
  update();
  if (has("status")) refresh();
  else $("#notice").textContent = "This entry does not declare a playback observation service.";
});
