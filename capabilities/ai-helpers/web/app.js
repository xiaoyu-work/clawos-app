ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  const form = document.querySelector("#summarize");
  const text = form.elements.text;
  text.oninput = () => { document.querySelector("#input-state").textContent = `${text.value.length} characters`; };
  function output(value) {
    document.querySelector("#result").textContent = value.summary;
    const details = [];
    if (value.model) details.push(`Model: ${value.model}`);
    if (value.provider) details.push(`Provider: ${value.provider}`);
    if (value.usage) details.push(`App-reported usage: ${value.usage.units} units`);
    if (value.budget) details.push(`App budget ${value.budget.period}: ${value.budget.units_used} / ${value.budget.units_cap} units`);
    document.querySelector("#usage").textContent = details.join(" - ");
  }
  form.onsubmit = (event) => {
    event.preventDefault();
    const submitted = text.value;
    if (!submitted.trim()) { document.querySelector("#notice").textContent = "Enter text to summarize."; return; }
    void ui.run(form.querySelector("button"), () => ClawApp.call("run", { text: submitted }), (value) => {
      document.querySelector("#summary-source").textContent = `Summary of the submitted ${submitted.length} characters. Input edits are not resubmitted automatically.`;
      output(value);
    }, document.querySelector("#notice"));
  };
  ui.allTools(document.querySelector("#more"), app, output);
});
