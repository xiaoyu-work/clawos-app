ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app); const form = document.querySelector("#request");
  const notice = document.querySelector("#notice");
  function output(value) {
    document.querySelector("#response-status").textContent = `HTTP ${value.status} - ${value.url}${value.truncated ?
      " - body truncated by the App" : ""}`;
    const headers = ui.node("dl", null, { class: "detail-grid" });
    for (const [name, text] of Object.entries(value.headers || {})) headers.append(ui.node("dt", name), ui.node("dd", text));
    ui.replace(document.querySelector("#response-headers"), [headers]);
    let body = value.body || "";
    try { body = JSON.stringify(JSON.parse(body), null, 2); } catch {}
    document.querySelector("#response").value = body;
  }
  form.onsubmit = (event) => {
    event.preventDefault();
    const args = { method: form.elements.method.value, url: form.elements.url.value };
    if (form.elements.data.value) args.data = form.elements.data.value;
    if (form.elements.header.value.trim()) args.header = form.elements.header.value.split(/\r?\n/).filter((line) => line.trim());
    args.timeout = Number(form.elements.timeout.value);
    void ui.run(form.querySelector("button"), () => ClawApp.call("fetch", args), output, notice);
  };
  const download = ui.node("button", "Download to file");
  download.disabled = !ClawApp.tool(app, "download");
  download.onclick = () => ui.command(app, "download", { url: form.elements.url.value }, (value) => {
    document.querySelector("#download-result").textContent = `Download reported: ${value.path || value.output} - ${value.bytes} bytes`;
  }, { title: "Download to an authorized path", submitLabel: "Download", fields: {
    url: { label: "Source URL", type: "url" },
    output: { label: "Canonical absolute destination", type: "text", placeholder: "/home/user/Downloads/file" },
  }, description: "The OS checks this App's network and exact file-write authority. A failed download preserves the old destination." });
  document.querySelector("#actions").append(download);
  ui.allTools(document.querySelector("#more"), app, (value) => {
    if (value.body !== undefined) output(value);
    else document.querySelector("#download-result").textContent = `Download reported: ${value.path || value.output} - ${value.bytes} bytes`;
  }, () => ({ url: form.elements.url.value }));
});
