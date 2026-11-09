ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  const path = document.querySelector("#path");
  const text = document.querySelector("#text");
  const notice = document.querySelector("#notice");
  let proposal = "";
  const defaults = () => ({ path: path.value, file: path.value, text: [text.value] });
  function output(value) {
    if (typeof value.content === "string") {
      document.querySelector("#preview").value = value.content;
      document.querySelector("#file-info").textContent = `${value.path} - ${value.format} - ${value.lines} extracted lines`;
      return;
    }
    if (value.size !== undefined) {
      document.querySelector("#file-info").textContent = `${value.path} - ${value.format} - ${value.size} bytes - ${
        value.readable ? "Parser available" : "No available parser for this file"}`;
      return;
    }
    if (value.output) {
      document.querySelector("#result").textContent = `Conversion reported: ${value.input} -> ${value.output} (${value.format})`;
      document.querySelector("#use-text").hidden = true;
      return;
    }
    proposal = value.summary || value.text || "";
    document.querySelector("#result").textContent = proposal;
    document.querySelector("#result-source").textContent = `Source: ${value.source || "Explicit input"}${
      value.model ? ` - Model: ${value.model}` : ""}. This result does not write or replace the source document.`;
    document.querySelector("#use-text").hidden = !proposal;
  }
  for (const [command, label] of [["read", "Read document"], ["info", "Document properties"], ["convert", "Convert format"]]) {
    const button = ui.node("button", label);
    button.disabled = !ClawApp.tool(app, command);
    button.onclick = () => {
      if (!path.value.trim()) { notice.textContent = "Enter an authorized document path."; return; }
      if (command === "convert") {
        const extension = path.value.split(".").at(-1).toLowerCase();
        if (!["json", "csv"].includes(extension)) {
          notice.textContent = "This client converts JSON arrays of objects to CSV, or CSV to JSON.";
          return;
        }
        const format = extension === "json" ? "csv" : "json";
        ui.command(app, command, { path: path.value, to: format }, output, {
          title: "Convert document", submitLabel: "Convert",
          description: `Write the ${format.toUpperCase()} sibling of this source. An existing output may be replaced; the source is unchanged.`,
          fields: { path: { label: "Source document", readOnly: true },
            to: { label: "Output format", choices: [format] } },
        });
      } else void ui.run(button, () => ClawApp.call(command, { path: path.value }), output, notice);
    };
    document.querySelector("#file-actions").append(button);
  }
  for (const [command, label] of [["summarize", "Summarize"], ["explain", "Explain"], ["rewrite", "Propose rewrite"]]) {
    const button = ui.node("button", label);
    button.disabled = !ClawApp.tool(app, command);
    button.onclick = () => {
      const file = document.querySelector("#input-source").value === "file";
      if (!(file ? path.value : text.value).trim()) {
        notice.textContent = file ? "Choose an authorized file." : "Enter the text to process.";
        return;
      }
      const arguments_ = file ? { file: path.value } : { text: [text.value] };
      if (command === "rewrite") arguments_.instruction = document.querySelector("#instruction").value;
      void ui.run(button, () => ClawApp.call(command, arguments_), output, notice);
    };
    document.querySelector("#ai-actions").append(button);
  }
  document.querySelector("#use-text").onclick = () => {
    text.value = proposal;
    document.querySelector("#input-source").value = "text";
    text.focus();
  };
  ui.allTools(document.querySelector("#more"), app, output, defaults);
});
