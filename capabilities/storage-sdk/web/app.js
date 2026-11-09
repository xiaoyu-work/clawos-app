ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi; ui.showApp(app);
  const notice = document.querySelector("#notice");
  const state = document.querySelector("#result-state");
  const target = document.querySelector("#result");
  function output(value) {
    if (Array.isArray(value.columns) && Array.isArray(value.rows)) {
      state.textContent = `${value.count} rows shown${value.truncated ? ` of ${value.total_rows}; the App bounded the result` : ""}. Database: ${value.database}`;
      ui.table(target, value.rows, value.columns.map((name, index) => ({ label: name, value: (row) => row[index] })));
    } else if (value.schema !== undefined) {
      document.querySelector("#schema").textContent = value.schema;
      state.textContent = `Schema for ${value.database}.${value.table}`;
    } else if (value.rows_affected !== undefined) {
      state.textContent = `Statement committed in ${value.database}; ${value.rows_affected < 0 ?
        "row count unavailable for this statement" : `${value.rows_affected} rows affected`}.`;
      ui.replace(target, [ui.node("pre", value.statement)]);
    } else if (value.data) {
      state.textContent = `${value.count} entries reported by App.`;
      ui.table(target, Object.entries(value.data), [
        { label: "Key", value: (item) => item[0] }, { label: "Value", value: (item) => item[1] },
      ]);
    } else ui.replace(target, [ui.node("pre", typeof value === "string" ? value : JSON.stringify(value, null, 2))]);
  }
  document.querySelector("#kv").hidden = app.id !== "kv";
  document.querySelector("#db").hidden = app.id !== "db";
  document.querySelector("#database-browser").hidden = app.id !== "db";
  if (app.id === "kv") {
    const key = document.querySelector("#key");
    const value = document.querySelector("#value");
    const showKeys = (result) => {
      const keys = Array.isArray(result) ? result : result.keys;
      state.textContent = `${keys.length} matching keys. Values are read only when selected.`;
      ui.replace(document.querySelector("#entries"), keys.map((name) => {
        const button = ui.node("button", name);
        button.onclick = () => { key.value = name; document.querySelector("#get").click(); };
        return button;
      }));
    };
    for (const item of [{ button: "get", command: "get" },
      { button: "set", command: "set" }, { button: "list", command: "list" }]) {
      const button = document.querySelector(`#${item.button}`);
      button.onclick = () => void ui.run(button, () => {
        const args = item.command === "list" ? { pattern: document.querySelector("#pattern").value } : { key: key.value };
        if (item.command === "set") args.value = value.value;
        return ClawApp.call(item.command, args);
      }, (result) => {
        if (item.command === "list") { showKeys(result); return; }
        if (item.command === "get") {
          value.value = result;
          state.textContent = `Get returned for "${key.value}". An empty string does not prove whether the key exists.`;
          ui.replace(target, [ui.node("pre", result)]);
        } else {
          state.textContent = `Set reported for "${result.key || key.value}".`;
          ui.replace(target, [ui.node("pre", result.value === undefined ? value.value : result.value)]);
        }
      }, notice);
    }
    document.querySelector("#delete").onclick = () => ui.command(app, "del", { key: key.value }, (result) => {
      state.textContent = result.deleted ? `Deleted "${result.key}".` : `No stored entry was deleted for "${result.key}".`;
      target.replaceChildren();
    }, { title: "Delete key?", submitLabel: "Delete key",
      description: "Remove only this exact key. No recovery is promised.", fields: { key: { label: "Key", readOnly: true } } });
  } else {
    const database = document.querySelector("#database");
    const sql = document.querySelector("#sql");
    let generation = 0;
    database.oninput = () => { ++generation; document.querySelector("#tables").replaceChildren(); document.querySelector("#schema").textContent = ""; };
    document.querySelector("#query").onclick = (event) => {
      const request = generation;
      void ui.run(event.target, () => ClawApp.call("query", { database: database.value, sql: sql.value }),
        (value) => { if (request === generation) output(value); }, notice);
    };
    document.querySelector("#execute").onclick = () => ui.command(app, "exec", {
      database: database.value, sql: sql.value,
    }, output, { title: "Execute one write statement?", submitLabel: "Execute and commit",
      description: "Review this exact statement and database. Writes are committed by the App; this is not a read-only query.",
      fields: { database: { label: "Database", readOnly: true }, sql: { label: "Statement", type: "textarea", rows: 8 } } });
    for (const [command, label] of [["databases", "List databases"], ["tables", "Load tables"]]) {
      const button = ui.node("button", label);
      button.onclick = () => {
        const request = generation;
        void ui.run(button, () => ClawApp.call(command, command === "tables" ? { database: database.value } : {}), (result) => {
          if (request !== generation) return;
          if (command === "databases") {
            ui.replace(document.querySelector("#databases"), result.databases.map((item) => {
              const choose = ui.node("button", null, { class: "card stack" });
              choose.append(ui.node("strong", item.name), ui.node("span", `${item.size} bytes - ${item.tables} tables`, { class: "muted small" }));
              choose.onclick = () => { database.value = item.name; database.oninput(); };
              return choose;
            }));
          } else ui.replace(document.querySelector("#tables"), result.tables.map((table) => {
            const choose = ui.node("button", table);
            choose.onclick = () => {
              const current = generation;
              void ui.run(choose, () => ClawApp.call("schema", { database: result.database, table }),
                (value) => { if (current === generation) output(value); }, notice);
            };
            return choose;
          }));
        }, notice);
      };
      document.querySelector("#db-actions").append(button);
    }
  }
  ui.allTools(document.querySelector("#more"), app, output);
});
