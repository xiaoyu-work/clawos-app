ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const $ = (selector) => document.querySelector(selector);
  const attached = app.id === "browser-attached";
  const search = app.id === "search";
  const reader = app.id === "web";
  const has = (command) => Boolean(ClawApp.tool(app, command));
  let busy = false;
  let selected = null;
  let generation = 0;
  let history = [];
  let historyIndex = -1;
  let currentUrl = "";
  ui.showApp(app);

  function checked(value) {
    ui.output($("#raw"), value);
    if (value && value.error) throw new Error(String(value.error));
    return value;
  }
  function call(command, args = {}) {
    const tool = ClawApp.tool(app, command);
    if (!tool) throw new Error(`This entry does not declare ${command}.`);
    return ClawApp.call(tool.name, args);
  }
  function httpUrl(value, base) {
    const url = new URL(value, base);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
      throw new Error("Use an HTTP or HTTPS URL without embedded credentials.");
    }
    return url.href;
  }
  function update() {
    $("#go").disabled = busy || attached && !selected || !search && !reader && !attached;
    $("#back").disabled = busy || historyIndex < 1;
    $("#forward").disabled = busy || historyIndex >= history.length - 1;
    $("#reload").disabled = busy || !currentUrl;
    $("#snapshot").disabled = busy || !selected || !has("snapshot");
    $("#activate").disabled = busy || !selected || !has("activate");
    $("#query-form").querySelector("button").disabled = busy || !selected || !has("query");
  }
  async function perform(action, render) {
    if (busy) return;
    busy = true;
    const controls = Array.from(document.querySelectorAll("button, input, select")).filter((control) => !control.disabled);
    controls.forEach((control) => { control.disabled = true; });
    await ui.run(null, async () => checked(await action()), render, $("#notice"));
    busy = false;
    controls.forEach((control) => { control.disabled = false; });
    update();
  }
  function empty(target, text) {
    ui.replace(target, [ui.node("p", text, { class: "empty" })]);
  }
  function clearPage(title) {
    $("#page-title").textContent = title;
    for (const id of ["#page-url", "#page-meta", "#page-content"]) $(id).textContent = "";
    $("#page-links").replaceChildren();
    $("#page-actions").replaceChildren();
    $("#dom-results").replaceChildren();
  }
  function modal(command, defaults, render, options) {
    if (busy || !has(command)) return;
    const version = generation;
    ui.command(app, command, defaults, (value) => {
      checked(value);
      if (version !== generation) return;
      render(value);
    }, options);
  }
  function pageAction(label, command, defaults, render, options) {
    if (!has(command)) return;
    const button = ui.node("button", label, { type: "button" });
    button.onclick = () => modal(command, defaults(), render, options);
    $("#page-actions").append(button);
  }
  function saved(value) {
    const path = value.saved || value.output;
    const confirmed = attached ? typeof value.saved === "string" && value.saved : value.ok === true && typeof value.output === "string" && value.output;
    $("#outcome").textContent = confirmed ? `Backend saved screenshot: ${path}${value.bytes == null ? "" : ` (${value.bytes} bytes)`}` :
      `No saved screenshot outcome confirmed${path ? ` (reported output: ${path})` : ""}. Inspect the backend response and destination before trying again.`;
  }
  function readerActions() {
    pageAction("Save page screenshot", "screenshot", () => ({ url: currentUrl }), saved, {
      title: "Save a web page screenshot", submitLabel: "Capture to file",
      description: "Uses this entry's headless browser, not the user's desktop. Review the exact output path; the Web backend may overwrite it.",
      fields: { url: { readOnly: true }, output: { label: "Authorized output file" } },
    });
    pageAction("Request AI summary", "summarize", () => ({ url: currentUrl }), (value) => {
      if (typeof value.summary !== "string") throw new Error("No summary was returned.");
      $("#page-content").textContent = value.summary;
      $("#page-meta").textContent = `AI summary of ${value.source_chars ?? "unknown"} source characters. Original page can be reloaded.`;
    }, {
      title: "Request an AI page summary", submitLabel: "Request summary",
      description: "Explicit AI request through this App's own consent and budget. This fetches the saved URL again; no provider fallback is used.",
      fields: { url: { readOnly: true } },
    });
  }
  function renderPage(value) {
    if (!value || typeof value.text !== "string") throw new Error("The backend returned no readable page text.");
    clearPage(value.title || "Untitled page");
    currentUrl = value.url || currentUrl;
    $("#page-url").textContent = currentUrl;
    $("#page-meta").textContent = [value.engine, value.warning].filter(Boolean).join(" - ");
    $("#page-content").textContent = value.text || "This page contains no extractable text.";
    const links = Array.isArray(value.links) ? value.links : [];
    for (const link of links) {
      let url;
      try { url = httpUrl(link.href, currentUrl); } catch { continue; }
      const button = ui.node("button", `${link.text || url} - ${url}`, { type: "button" });
      button.onclick = () => load(url);
      $("#page-links").append(button);
    }
    readerActions();
  }
  function load(url, index) {
    if (busy) return;
    void perform(() => call("read", { url: httpUrl(url) }), (value) => {
      renderPage(value);
      generation++;
      $("#address").value = currentUrl;
      if (index === undefined) {
        history = history.slice(0, historyIndex + 1);
        history.push(currentUrl);
        historyIndex = history.length - 1;
      } else historyIndex = index;
      $("#outcome").textContent = "Page text loaded. Returned HTML is never executed in this view.";
    });
  }
  function renderSearch(value) {
    if (!value || !Array.isArray(value.results)) throw new Error("The search backend returned no result list.");
    clearPage("Select a search result");
    generation++;
    const results = value.results;
    $("#outcome").textContent = `${results.length} ${$("#search-kind").value === "image" ? "image" : "web"} results via ${value.provider} for "${value.query}".`;
    ui.replace($("#results"), results.map((item) => {
      const card = ui.node("article", null, { class: "card stack" });
      card.append(ui.node("h2", item.title || "Untitled result", { class: "prose" }), ui.node("p", item.url, { class: "prose" }),
        ui.node("p", item.snippet || item.source || "", { class: "prose" }));
      if (item.width || item.height) card.append(ui.node("p", `${item.width} x ${item.height}`, { class: "muted small" }));
      const button = ui.node("button", "Select result", { type: "button" });
      button.onclick = () => {
        clearPage(item.title || "Selected result");
        $("#page-url").textContent = item.url || "";
        $("#page-content").textContent = item.snippet || item.source || "No description supplied.";
        $("#page-meta").textContent = item.thumbnail ?
          "Image URLs are metadata only. This entry does not fetch or display remote images." :
          "This search entry does not declare page reading or tab navigation.";
      };
      card.append(button);
      return card;
    }));
    if (!results.length) empty($("#results"), "No matches. Change the query or explicitly choose another provider.");
  }
  function selectTab(tab) {
    if (busy) return;
    selected = tab;
    generation++;
    clearPage(tab.title || `Tab ${tab.id}`);
    $("#address").value = tab.url;
    $("#page-url").textContent = tab.url;
    $("#page-meta").textContent = `Tab ${tab.id}${tab.active ? " - active in its window" : ""}. Selection does not change browser focus.`;
    for (const button of $("#tabs").querySelectorAll("button")) {
      button.classList.toggle("selected", button.dataset.tabId === String(tab.id));
    }
    pageAction("Save visible tab screenshot", "screenshot", () => ({
      tab_id: tab.id, page_url: tab.url,
    }), saved, {
      title: "Capture selected tab to a new PNG", submitLabel: "Capture tab",
      description: "This operation brings the tab and its window to the foreground. The output must be a new authorized path. It is not a desktop screenshot.",
      fields: { tab_id: { readOnly: true }, page_url: { readOnly: true } },
    });
    update();
  }
  function refreshTabs() {
    void perform(() => call("list"), (value) => {
      if (!Array.isArray(value.tabs)) throw new Error("The backend returned no tab list.");
      const previousId = selected && selected.id;
      selected = null;
      generation++;
      clearPage("Select an open tab");
      ui.replace($("#tabs"), value.tabs.map((tab) => {
        const button = ui.node("button", `${tab.active ? "[Active] " : ""}${tab.title || "Untitled"} - ${tab.url}`, {
          type: "button", "data-tab-id": tab.id,
        });
        button.onclick = () => selectTab(tab);
        return button;
      }));
      if (!value.tabs.length) empty($("#tabs"), "No tabs reported. This entry needs its authorized browser bridge.");
      $("#outcome").textContent = previousId ? "Tabs refreshed. Reselect a tab to bind controls to its latest reported URL." : "";
    });
  }
  function renderElements(value, target) {
    if (!Array.isArray(value.matches)) throw new Error("No element matches were returned.");
    $("#outcome").textContent = `${value.matches.length} of ${value.total} matching elements${value.truncated ? " (bounded result)" : ""}.`;
    ui.replace($("#dom-results"), value.matches.map((item) => {
      const card = ui.node("article", null, { class: "card stack" });
      card.append(ui.node("h3", `${item.tag} ${item.attrs && (item.attrs["aria-label"] || item.attrs.name) || ""}`),
        ui.node("p", item.text || (item.secret ? "Sensitive field: current value is not exposed." : "No visible text."), { class: "prose" }),
        ui.node("p", item.visible ? "Visible when queried" : "Not visible when queried", { class: "muted small" }));
      const version = generation;
      function action(label, command, extra, options) {
        if (!has(command)) return;
        const button = ui.node("button", label, { type: "button" });
        button.onclick = () => {
          if (busy || version !== generation || !selected || selected.id !== target.id || selected.url !== target.url) return;
          selected = null;
          generation++;
          $("#dom-results").replaceChildren();
          $("#page-actions").replaceChildren();
          update();
          modal(command, { tab_id: target.id, page_url: target.url, reference: item.ref, ...extra }, (result) => {
            $("#outcome").textContent = result.clicked === true ? "Click reported by the backend. Refresh tabs before another page action." :
              result.filled === true ? "Field fill reported. Query again to obtain fresh element references." : "Action outcome was not confirmed.";
            generation++;
            $("#dom-results").replaceChildren();
            $("#page-actions").replaceChildren();
            selected = null;
            update();
          }, {
            title: label, submitLabel: label,
            description: "Targets this queried element on the selected tab's reported page. A changed page or stale reference must be queried again. No automatic retry.",
            fields: { tab_id: { readOnly: true }, page_url: { readOnly: true }, reference: { readOnly: true },
              value: { label: item.secret ? "Secret value (requires its own approval)" : "Text to enter", type: item.secret ? "password" : "textarea", allowEmpty: true, includeEmpty: true } },
            ...options,
          });
        };
        card.append(button);
      }
      action("Click element", "click", {});
      if (["input", "textarea", "select"].includes(item.tag)) {
        action(item.secret ? "Fill sensitive field" : "Fill field", item.secret ? "fill_secret" : "fill", { value: "" });
      }
      return card;
    }));
    if (!value.matches.length) empty($("#dom-results"), "No elements match this selector.");
  }

  $("#search-options").hidden = !search;
  $("#provider").required = search;
  $("#limit").required = search;
  $("#tabs-section").hidden = !attached;
  $("#inspect").hidden = !attached;
  $("#reader-controls").hidden = !reader;
  $("#address-label").textContent = search ? "Search query" : attached ? "Navigate selected tab to" : "Read a web address";
  $("#address").placeholder = search ? "What would you like to find?" : "https://example.com";
  $("#address").maxLength = search ? 2048 : 8192;
  $("#go").textContent = search ? "Search" : attached ? "Navigate selected tab" : "Read page";
  $("#scope").textContent = search ? "Explicit-provider search. No attached-browser login state, remote image loading or automatic provider switching." :
    reader ? "Headless page text and links, not an embedded desktop browser. Navigation is handled only by this entry's Web backend." :
      "Controls the authorized attached browser. This view does not render a remote browser or create new tabs.";
  $("#navigation-help").textContent = attached ? "Refresh and select a tab first. Navigation changes the real selected tab." :
    search ? "Select a provider for every search; configured credentials and network grants are enforced by the OS." :
      "Include http:// or https://. The backend may explicitly report its non-JavaScript urllib fallback.";
  $("#navigation").onsubmit = (event) => {
    event.preventDefault();
    if (busy || !$("#navigation").reportValidity()) return;
    if (search) {
      void perform(() => call($("#search-kind").value, {
        provider: $("#provider").value, query: $("#address").value, max_results: Number($("#limit").value),
      }), renderSearch);
    } else if (reader) load($("#address").value);
    else if (selected) {
      const target = { ...selected };
      selected = null;
      generation++;
      clearPage("Navigation pending - refresh tabs before inspecting again");
      void perform(() => call("go", { tab_id: target.id, url: httpUrl($("#address").value) }), (value) => {
        if (value.navigated !== target.id) throw new Error("Navigation was not confirmed. Refresh tabs before trying again.");
        generation++;
        selected = null;
        clearPage("Navigation reported - refresh tabs before inspecting");
        $("#outcome").textContent = `Tab ${target.id} navigation requested: ${value.url}. The page may still be loading.`;
      });
    }
  };
  $("#refresh-tabs").onclick = refreshTabs;
  $("#back").onclick = () => load(history[historyIndex - 1], historyIndex - 1);
  $("#forward").onclick = () => load(history[historyIndex + 1], historyIndex + 1);
  $("#reload").onclick = () => load(currentUrl, historyIndex);
  $("#snapshot").onclick = () => {
    if (!selected) return;
    const target = { ...selected };
    void perform(() => call("snapshot", { tab_id: target.id, page_url: target.url, kind: "text" }), (value) => {
      if (typeof value.text !== "string") throw new Error("The backend returned no page text.");
      $("#page-title").textContent = value.title || "Untitled page";
      $("#page-url").textContent = value.url || target.url;
      $("#page-content").textContent = value.text || "No extractable text.";
      $("#page-meta").textContent = "Bounded plain-text snapshot; editable and sensitive values are redacted by the backend.";
      if (value.url && value.url !== target.url) {
        selected = null;
        generation++;
        $("#dom-results").replaceChildren();
        $("#page-actions").replaceChildren();
        $("#outcome").textContent = "The reported page URL changed. Refresh tabs and reselect before further actions.";
      }
    });
  };
  $("#activate").onclick = () => {
    if (!selected) return;
    const id = selected.id;
    void perform(() => call("activate", { tab_id: id }), (value) => {
      $("#outcome").textContent = value.activated === id ? `Tab ${id} activation reported.` : "Tab activation was not confirmed.";
    });
  };
  $("#query-form").onsubmit = (event) => {
    event.preventDefault();
    if (!selected || !$("#query-form").reportValidity()) return;
    const target = { ...selected };
    generation++;
    $("#dom-results").replaceChildren();
    void perform(() => call("query", { tab_id: target.id, page_url: target.url, selector: $("#selector").value }),
      (value) => renderElements(value, target));
  };
  if (search) empty($("#results"), "Choose a provider and search to see results.");
  update();
  if (attached && has("list")) refreshTabs();
});
