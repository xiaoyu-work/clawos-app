(function () {
  "use strict";

  const protocol = "claw.web-app/v1";
  const pending = new Map();
  let context = null;
  let sequence = 0;
  let readyResolve;
  const ready = new Promise((resolve) => { readyResolve = resolve; });

  window.addEventListener("message", (event) => {
    if (event.source !== window.parent || !event.data || event.data.protocol !== protocol) return;
    const message = event.data;
    if (message.type === "init" && !context) {
      if (typeof message.nonce !== "string" || !message.app || !Array.isArray(message.app.tools)) return;
      context = { nonce: message.nonce, origin: event.origin, app: message.app };
      document.documentElement.dataset.theme = message.theme === "light" ? "light" : "dark";
      readyResolve(context.app);
      return;
    }
    if (!context || event.origin !== context.origin || message.nonce !== context.nonce) return;
    if (message.type === "theme") {
      document.documentElement.dataset.theme = message.theme === "light" ? "light" : "dark";
      return;
    }
    if (message.type !== "result" || typeof message.id !== "string") return;
    const request = pending.get(message.id);
    if (!request) return;
    pending.delete(message.id);
    clearTimeout(request.timer);
    if (message.ok) request.resolve(message.result);
    else request.reject(new Error(typeof message.error === "string" ? message.error : "App call failed"));
  });

  function unwrap(value) {
    if (value && value.structuredContent !== undefined) return value.structuredContent;
    if (value && Array.isArray(value.content)) {
      const text = value.content.filter((item) => item.type === "text").map((item) => item.text).join("\n");
      if (value.isError) throw new Error(text || "App reported an error");
      try { return JSON.parse(text); } catch { return text || value; }
    }
    return value;
  }

  async function call(name, arguments_) {
    const app = await ready;
    const matches = app.tools.filter((tool) => tool.name === name || tool.command === name);
    if (matches.length !== 1) throw new Error(`This App does not declare ${name}.`);
    const id = `web-${++sequence}`;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error("The call outcome is not confirmed. Check the App state before trying again."));
      }, 125000);
      pending.set(id, { resolve: (value) => {
        try { resolve(unwrap(value)); } catch (error) { reject(error); }
      }, reject, timer });
      window.parent.postMessage({
        protocol, type: "call", nonce: context.nonce, id,
        tool: matches[0].name, arguments: arguments_ || {},
      }, context.origin);
    });
  }

  function tool(app, name) {
    const matches = app.tools.filter((item) => item.name === name || item.command === name);
    return matches.length === 1 ? matches[0] : null;
  }

  window.ClawApp = Object.freeze({ ready, call, unwrap, tool });
  window.parent.postMessage({ protocol, type: "ready" }, "*");
}());
