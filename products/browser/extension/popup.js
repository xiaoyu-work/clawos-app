const CHAT_HOST = "com.yuos.browser_chat";
const MAX_MESSAGES = 20;
const MAX_SAVED_TEXT = 16 * 1024;
const elements = Object.fromEntries([
  "access", "composer", "empty", "include-tab", "messages", "new-chat",
  "prompt", "reconnect", "send", "site", "status", "stop", "summarize", "transcript",
].map((id) => [id, document.getElementById(id)]));

let windowId;
let storageKey;
let conversationRevision = 0;
let ready = false;
let tab = null;
let tabRevision = 0;
let accessPaused = null;
let sessionId;
let messages = [];
let turn;
let stream;
let cancelPort;
let retired = false;

function status(text, error = false) {
  elements.status.textContent = text;
  elements.status.hidden = !text;
  elements.status.dataset.tone = error ? "error" : "";
}

function updateControls() {
  const canUseTab = ready && Boolean(tab) && accessPaused !== true;
  elements["include-tab"].disabled = !canUseTab;
  if (!canUseTab) elements["include-tab"].checked = false;
  elements.summarize.disabled = !canUseTab || Boolean(turn);
  elements.site.textContent = tab ? new URL(tab.page_url).host : "";
  elements.site.title = tab?.page_url || "";
  elements.access.disabled = accessPaused === null;
  elements.access.textContent = accessPaused ? "Resume tab access" : "Pause tab access";
  elements["new-chat"].disabled = !ready || Boolean(turn);
  elements.send.hidden = Boolean(turn);
  elements.send.disabled = !ready || !elements.prompt.value.trim();
  elements.stop.hidden = !turn;
  elements.stop.disabled = Boolean(turn?.stopping);
  elements.reconnect.hidden = !turn?.taskId || Boolean(stream);
}

async function currentTab() {
  const [active] = await chrome.tabs.query({ active: true, windowId });
  if (!active?.url || !Number.isInteger(active.id) || active.incognito || active.pendingUrl) return null;
  const url = new URL(active.url);
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;
  return { tab_id: active.id, page_url: url.origin };
}

function sameTab(first, second) {
  return first?.tab_id === second?.tab_id && first?.page_url === second?.page_url;
}

async function refreshTab() {
  if (windowId === undefined) return;
  const revision = ++tabRevision;
  let next;
  try { next = await currentTab(); } catch (_) { next = null; }
  if (revision !== tabRevision) return;
  if (!sameTab(tab, next)) elements["include-tab"].checked = false;
  tab = next;
  updateControls();
}

function saveChat() {
  if (retired) return;
  chrome.storage.session.set({
    [storageKey]: {
      sessionId,
      messages: messages.map(({ role, text }) => ({ role, text: text.slice(0, MAX_SAVED_TEXT) })),
      turn: turn && { taskId: turn.taskId, stopping: turn.stopping },
    },
  }).catch(() => {});
}

function showMessages() {
  elements.empty.hidden = messages.length > 0;
  elements.messages.replaceChildren(...messages.map(({ role, text }) => {
    const row = document.createElement("div");
    row.className = `message ${role}`;
    row.textContent = text;
    row.hidden = !text;
    return row;
  }));
  elements.transcript.scrollTop = elements.transcript.scrollHeight;
}

function showAnswer(text) {
  const view = elements.transcript;
  const atBottom = view.scrollHeight - view.scrollTop - view.clientHeight < 40;
  messages.at(-1).text = text;
  elements.messages.lastElementChild.hidden = !text;
  elements.messages.lastElementChild.textContent = text;
  if (atBottom) view.scrollTop = view.scrollHeight;
}

function finish(text, error = false) {
  const connection = stream;
  const cancellation = cancelPort;
  stream = undefined;
  cancelPort = undefined;
  if (!messages.at(-1)?.text) {
    messages.pop();
    showMessages();
  }
  turn = undefined;
  connection?.disconnect();
  cancellation?.disconnect();
  saveChat();
  status(text, error);
  updateControls();
}

function interrupted(message) {
  if (!turn.taskId) {
    finish(message, true);
    return;
  }
  const connection = stream;
  stream = undefined;
  connection?.disconnect();
  status(`${message} Reconnect to the same task.`, true);
  updateControls();
}

function openStream(request) {
  let connection;
  try {
    connection = chrome.runtime.connectNative(CHAT_HOST);
    stream = connection;
    connection.onMessage.addListener(({ event, data }) => {
      if (stream !== connection || !turn) return;
      switch (event) {
        case "task":
          if (turn.taskId && turn.taskId !== data.task_id) {
            interrupted("Yu OS Agent returned a different task.");
            return;
          }
          turn.taskId = data.task_id;
          sessionId = data.session_id || sessionId;
          saveChat();
          if (turn.stopping) requestCancel();
          break;
        case "task_status":
          turn.status = data.status;
          if (turn.stopping) break;
          status({
            pending: "Queued...",
            running: "Working...",
            waiting_approval: "Waiting for approval in Yu OS.",
          }[data.status] || "Working...");
          break;
        case "tool_start":
          if (!turn.stopping && turn.status === "running") status(`Using ${data.name || "a tool"}...`);
          break;
        case "delta":
          turn.answer += data.text;
          if (!turn.stopping) showAnswer(turn.answer);
          break;
        case "done":
          showAnswer(data.answer ?? (turn.answer || messages.at(-1).text));
          finish("");
          return;
        case "error":
          if (data.task_status === "cancelled") {
            finish("Stopped.");
          } else if (data.task_status === "error" || !turn.taskId) {
            finish(data.message || "Agent task failed.", true);
          } else {
            interrupted(data.message || "The Agent stream ended.");
          }
          return;
        case "transport_error":
          interrupted(data.message);
          return;
      }
      updateControls();
    });
    connection.onDisconnect.addListener(() => {
      const error = chrome.runtime.lastError;
      if (stream !== connection || !turn) return;
      stream = undefined;
      const message = error
        ? "Browser chat is unavailable. Check the Yu OS Agent bridge and extension registration."
        : "The Agent connection closed before returning a result.";
      interrupted(message);
    });
    connection.postMessage(request);
    status(turn.stopping ? "Stopping..." : "Connecting to Yu OS Agent...");
    updateControls();
  } catch (_) {
    interrupted("Browser chat could not connect to Yu OS.");
  }
}

function streamTask() {
  if (!turn?.taskId || stream) return;
  turn.answer = "";
  if (!turn.stopping) showAnswer("");
  openStream({ action: "stream", task_id: turn.taskId });
}

function requestCancel() {
  if (!turn?.taskId || cancelPort) return;
  const target = turn;

  function cancelFailed(message) {
    if (turn !== target) return;
    target.stopping = false;
    if (target.answer) showAnswer(target.answer);
    saveChat();
    status(message, true);
    updateControls();
  }

  try {
    const connection = chrome.runtime.connectNative(CHAT_HOST);
    cancelPort = connection;
    connection.onMessage.addListener(({ event, data }) => {
      if (cancelPort !== connection) return;
      cancelPort = undefined;
      connection.disconnect();
      if (turn !== target) return;
      if (event !== "cancel") {
        cancelFailed(data.message || "Could not stop the task.");
        return;
      }
      if (!data.cancelled && !data.cancel_requested && !["ok", "error", "cancelled"].includes(data.status)) {
        cancelFailed("Yu OS Agent did not confirm cancellation.");
        return;
      }
      streamTask();
    });
    connection.onDisconnect.addListener(() => {
      void chrome.runtime.lastError;
      if (cancelPort !== connection) return;
      cancelPort = undefined;
      cancelFailed("Could not confirm cancellation. The task may still be running.");
    });
    connection.postMessage({ action: "cancel", task_id: target.taskId });
  } catch (_) {
    cancelPort?.disconnect();
    cancelPort = undefined;
    cancelFailed("Could not reach Yu OS Agent to stop the task.");
  }
}

async function sendMessage(prompt, includeTab) {
  prompt = prompt.trim();
  if (!ready || !prompt || turn) return;
  if (new TextEncoder().encode(prompt).length > 32 * 1024) {
    status("Message exceeds 32 KiB.", true);
    return;
  }
  const request = { action: "chat", prompt };
  const revision = conversationRevision;
  if (includeTab) {
    const selected = tab;
    let live;
    try { live = await currentTab(); } catch (_) { live = null; }
    if (turn || revision !== conversationRevision) return;
    if (accessPaused || !selected || !sameTab(selected, live) || !sameTab(tab, live)) {
      await refreshTab();
      status("The selected tab changed or is unavailable. Select it again to continue.", true);
      return;
    }
    request.tab = live;
  }
  if (sessionId) request.session_id = sessionId;
  messages = [
    ...messages.slice(-(MAX_MESSAGES - 2)),
    { role: "user", text: prompt },
    { role: "assistant", text: "" },
  ];
  turn = { answer: "", stopping: false };
  if (elements.prompt.value.trim() === prompt) elements.prompt.value = "";
  saveChat();
  showMessages();
  openStream(request);
}

elements.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  void sendMessage(elements.prompt.value, elements["include-tab"].checked);
});
elements.prompt.addEventListener("input", updateControls);
elements.prompt.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing && ready && !turn) {
    event.preventDefault();
    elements.composer.requestSubmit();
  }
});
elements.summarize.addEventListener("click", () => {
  elements["include-tab"].checked = true;
  void sendMessage("Summarize this page.", true);
});
elements["new-chat"].addEventListener("click", () => {
  if (turn || !ready) return;
  conversationRevision++;
  sessionId = undefined;
  messages = [];
  elements["include-tab"].checked = false;
  saveChat();
  showMessages();
  status("");
  elements.prompt.focus();
});
elements.stop.addEventListener("click", () => {
  if (!turn || turn.stopping) return;
  turn.stopping = true;
  saveChat();
  status("Stopping...");
  updateControls();
  requestCancel();
});
elements.reconnect.addEventListener("click", streamTask);
elements.access.addEventListener("click", async () => {
  const action = accessPaused ? "resume" : "pause";
  try {
    const result = await chrome.runtime.sendMessage({ browserAccess: action });
    if (result.error) throw new Error("Browser access did not change.");
    accessPaused = result.paused;
  } catch (_) {
    status("Could not change browser access.", true);
  }
  updateControls();
});
chrome.tabs.onActivated.addListener((info) => {
  if (info.windowId === windowId) void refreshTab();
});
chrome.tabs.onUpdated.addListener((_, change, updated) => {
  if (updated.windowId === windowId && updated.active && (change.url || change.status)) void refreshTab();
});
chrome.tabs.onRemoved.addListener((_, info) => {
  if (info.windowId === windowId) void refreshTab();
});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "session" && changes.browserAccessPaused) {
    accessPaused = Boolean(changes.browserAccessPaused.newValue);
    updateControls();
  }
});

async function initialize() {
  const window = await chrome.windows.getCurrent();
  if (window.incognito) {
    status("Yu OS Agent chat is unavailable in private windows.", true);
    return;
  }
  windowId = window.id;
  storageKey = `browserChat:${windowId}`;
  chrome.windows.onRemoved.addListener((id) => {
    if (id === windowId) retired = true;
  });
  const stored = await chrome.storage.session.get([storageKey, "browserAccessPaused"]);
  accessPaused = Boolean(stored.browserAccessPaused);
  if (stored[storageKey]) {
    ({ sessionId, messages, turn } = stored[storageKey]);
    if (turn) turn.answer = "";
  }
  ready = true;
  showMessages();
  await refreshTab();
  if (turn?.taskId) {
    streamTask();
  } else if (turn) {
    finish("No task confirmation was received. Check Yu OS Agent before trying again.", true);
  }
}

initialize().catch(() => status("Yu OS Agent could not open this side panel.", true));
