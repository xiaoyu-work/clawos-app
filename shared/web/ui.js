(function () {
  "use strict";
  function node(tag, text, attributes) {
    const result = document.createElement(tag);
    if (text !== undefined && text !== null) result.textContent = String(text);
    for (const [name, value] of Object.entries(attributes || {})) {
      if (name === "class") result.className = value;
      else result.setAttribute(name, String(value));
    }
    return result;
  }
  function replace(target, children) {
    target.replaceChildren(...children);
  }
  function rows(value, keys) {
    if (Array.isArray(value)) return value;
    for (const key of keys || ["items", "results", "entries", "events", "messages"]) {
      if (value && Array.isArray(value[key])) return value[key];
    }
    return [];
  }
  function table(target, items, columns, action) {
    if (!items.length) {
      replace(target, [node("div", "No items to display.", { class: "empty" })]);
      return;
    }
    const element = node("table");
    const head = node("tr");
    for (const column of columns) head.append(node("th", column.label));
    if (action) head.append(node("th", ""));
    element.append(head);
    for (const item of items) {
      const row = node("tr");
      for (const column of columns) {
        const value = typeof column.value === "function" ? column.value(item) : item[column.key];
        row.append(node("td", value == null ? "" : typeof value === "object" ? JSON.stringify(value) : value));
      }
      if (action) {
        const cell = node("td");
        const button = node("button", action.label);
        button.onclick = () => action.run(item);
        cell.append(button);
        row.append(cell);
      }
      element.append(row);
    }
    replace(target, [element]);
  }
  async function run(button, action, onResult, notice) {
    if (button) button.disabled = true;
    if (notice) { notice.textContent = "Working..."; notice.classList.remove("error"); }
    try {
      const result = await action();
      if (onResult) await onResult(result);
      if (notice) notice.textContent = "";
      return result;
    } catch (error) {
      if (notice) { notice.textContent = error.message; notice.classList.add("error"); }
      return undefined;
    } finally {
      if (button) button.disabled = false;
    }
  }
  function output(target, result) {
    replace(target, [node("pre", typeof result === "string" ? result : JSON.stringify(result, null, 2))]);
  }
  function fields(form) {
    const result = {};
    for (const element of form.elements) {
      if (!element.name || element.disabled) continue;
      if (element.type === "checkbox") result[element.name] = element.checked;
      else if (element.value !== "") {
        result[element.name] = element.type === "number" ? Number(element.value) : element.value;
      }
    }
    return result;
  }
  function showApp(app) {
    const label = document.querySelector("[data-app-label]");
    if (label) label.textContent = `${typeof app.name === "string" ? app.name : app.id} · ${app.id}`;
  }
  function command(app, name, defaults, onResult) {
    const tool = ClawApp.tool(app, name);
    if (!tool) throw new Error(`This App entry does not declare ${name}.`);
    const dialog = node("dialog");
    dialog.append(node("h2", tool.name));
    dialog.append(node("p", tool.description || "", { class: "muted small" }));
    const form = node("form");
    const inputs = [];
    for (const argument of tool.args || []) {
      const label = node("label", argument.name);
      const type = argument.kind;
      const complex = ["json", "object", "list", "array"].includes(type);
      const input = node(complex || type === "text" ? "textarea" : "input");
      input.name = argument.name;
      if (!complex) input.type = type === "bool" || type === "boolean" ? "checkbox" :
        ["int", "integer", "number", "float"].includes(type) ? "number" :
        /password|secret|bearer|hmac/.test(argument.name) ? "password" : "text";
      const value = defaults && defaults[argument.name] !== undefined ? defaults[argument.name] : argument.default;
      if (input.type === "checkbox") input.checked = value === true;
      else if (value !== undefined && value !== null) input.value = complex ? JSON.stringify(value, null, 2) : String(value);
      input.required = argument.required === true && input.type !== "checkbox";
      if (argument.description) label.append(node("span", argument.description, { class: "muted" }));
      label.append(input);
      form.append(label);
      inputs.push({ input, complex });
    }
    const notice = node("p", "", { class: "notice" });
    const actions = node("div", null, { class: "toolbar" });
    const cancel = node("button", "Cancel", { type: "button" });
    const execute = node("button", "Run", { type: "submit", class: "primary" });
    cancel.onclick = () => dialog.close();
    actions.append(cancel, execute);
    form.append(notice, actions);
    form.onsubmit = (event) => {
      event.preventDefault();
      const arguments_ = {};
      try {
        for (const { input, complex } of inputs) {
          if (input.type === "checkbox") arguments_[input.name] = input.checked;
          else if (input.value !== "") arguments_[input.name] = complex ? JSON.parse(input.value) :
            input.type === "number" ? Number(input.value) : input.value;
        }
      } catch {
        notice.textContent = "Enter valid JSON for structured fields.";
        notice.classList.add("error");
        return;
      }
      void run(execute, () => ClawApp.call(tool.name, arguments_), async (result) => {
        if (onResult) await onResult(result);
        dialog.close();
      }, notice);
    };
    dialog.append(form);
    dialog.addEventListener("close", () => dialog.remove());
    document.body.append(dialog);
    dialog.showModal();
  }
  function actions(target, app, names, onResult, defaults) {
    for (const item of names) {
      const name = typeof item === "string" ? item : item.command;
      const tool = ClawApp.tool(app, name);
      if (!tool) continue;
      const button = node("button", typeof item === "string" ? name : item.label);
      button.onclick = () => command(app, tool.name, defaults && defaults(), onResult);
      target.append(button);
    }
  }
  function allTools(target, app, onResult, defaults) {
    const details = node("details", null, { class: "card" });
    details.append(node("summary", "Additional App tools"));
    const buttons = node("div", null, { class: "toolbar" });
    buttons.style.marginTop = "12px";
    actions(buttons, app, app.tools.map((tool) => ({ command: tool.name, label: tool.command })), onResult, defaults);
    if (!app.tools.length) buttons.append(node("p",
      "This is a native-only entry. It does not declare an Agent-callable App service.", { class: "muted small" }));
    details.append(buttons);
    target.append(details);
  }
  window.ClawUi = Object.freeze({ node, replace, rows, table, run, output, fields, showApp, command, actions, allTools });
}());
