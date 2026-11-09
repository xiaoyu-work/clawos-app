ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const $ = (selector) => document.querySelector(selector);
  const tool = ClawApp.tool(app, "capture");
  let busy = false;
  const history = [];
  ui.showApp(app);
  $("#capture").disabled = !tool;
  if (!tool) $("#notice").textContent = "This entry declares no capture service.";
  $("#capture-form").onsubmit = (event) => {
    event.preventDefault();
    if (busy || !tool || !$("#capture-form").reportValidity()) return;
    const directory = $("#directory").value.trim();
    if (directory && (!directory.startsWith("/") || directory.includes("\0"))) {
      $("#notice").textContent = "Enter an existing authorized absolute Linux directory, or leave it blank for the Host-resolved default.";
      $("#notice").classList.add("error");
      return;
    }
    const args = { interactive: false, modal: $("#modal").checked };
    if (directory) args.save_dir = directory;
    busy = true;
    const controls = Array.from($("#capture-form").querySelectorAll("button, input, select"));
    controls.forEach((control) => { control.disabled = true; });
    ui.replace($("#result"), [ui.node("h3", "Capture requested once"), ui.node("p",
      "Waiting for an authoritative path or cancellation. If this call fails or times out, the outcome may be unknown; no retry is automatic.")]);
    void ui.run(null, () => ClawApp.call(tool.name, args), (value) => {
      ui.output($("#raw"), value);
      if (value && value.error) throw new Error(String(value.error));
      const received = new Date().toLocaleTimeString();
      let title;
      let detail;
      if (value?.cancelled === true) {
        title = "Capture cancelled";
        detail = "The service explicitly reported cancellation. No saved screenshot is claimed.";
      } else if (value?.cancelled === false && typeof value.path === "string" && value.path) {
        title = "PNG path returned by the service";
        detail = value.path;
      } else {
        title = "No saved output confirmed";
        detail = "The response contains neither an explicit cancellation nor a confirmed saved path. Inspect the response and destination before retrying.";
      }
      ui.replace($("#result"), [ui.node("h3", title), ui.node("p", detail, { class: "prose" }),
        ui.node("p", `Response received locally at ${received}.`, { class: "muted small" })]);
      history.unshift({ title, detail, received });
      history.splice(20);
      ui.replace($("#history"), history.map((entry) => {
        const card = ui.node("article", null, { class: "card stack" });
        card.append(ui.node("h3", entry.title), ui.node("p", entry.detail, { class: "prose" }),
          ui.node("p", `Local response time: ${entry.received}`, { class: "muted small" }));
        return card;
      }));
    }, $("#notice")).then((value) => {
      if (value === undefined) ui.replace($("#result"), [ui.node("h3", "Capture failed or unconfirmed"), ui.node("p",
        "See the service error below. No saved path or cancellation was confirmed; inspect the destination before trying again.")]);
    }).finally(() => {
      busy = false;
      controls.forEach((control) => { control.disabled = false; });
    });
  };
});
