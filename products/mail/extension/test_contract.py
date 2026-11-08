"""Execute real UI request builders against deterministic Thunderbird stubs."""

import json
from pathlib import Path
import subprocess


HERE = Path(__file__).parent
MANIFEST = json.loads((HERE.parent / "apps" / "mail-ai" / "app.json").read_text())


def test_protocol_pair_version_advances_without_identity_aliases():
    extension = json.loads((HERE / "manifest.json").read_text())
    assert extension["version"] == MANIFEST["version"]
    assert tuple(map(int, extension["version"].split("."))) > (0, 1, 0)
    assert extension["browser_specific_settings"]["gecko"]["id"] == "claw-mail-ai@claw.os"
    assert MANIFEST["id"] == "mail-ai"


UI_DRIVER = r"""
const fs = require("fs");
const vm = require("vm");
const root = process.argv[1];
const requests = [];
const recent = [{id: 12, sender: "alex", subject: "Review", date: "Friday"}];
const history = {};
const noop = () => {};
function element() {
  return {
    value: "hello", textContent: "", innerHTML: "", scrollHeight: 0,
    appendChild: noop, remove: noop, addEventListener: noop,
    classList: {add: noop, remove: noop},
  };
}
function context() {
  const elements = {};
  const ui = {
    aiCall: async (verb, args) => {
      requests.push({verb, args});
      // Only chat needs rendering here, to verify the response-field contract.
      return verb === "chat" ? {ok: true, result: {answer: "Friday [1]."}} : {ok: false};
    },
    showBusy: noop, clearBusy: noop, showError: noop, el: element,
    localiseDom: noop, copyToClipboard: noop,
    getSettings: async () => ({summarize: {}, features: {}}),
    setSettings: async () => {},
  };
  const messages = {
    getBody: async () => ({plain: "Review please", from: "alex", subject: "Q3"}),
    getDisplayedMessage: async () => ({id: 12}),
    getComposeDetails: async () => ({
      to: ["alex"], subject: "Review", body: "Hello", isPlainText: true,
    }),
    bodyToPlain: text => text,
  };
  return vm.createContext({
    window: {ClawUI: ui, ClawMessages: messages}, ClawUI: ui, console,
    document: {
      addEventListener: noop,
      getElementById: id => elements[id] ||= element(),
      querySelectorAll: () => [],
    },
    browser: {
      i18n: {getUILanguage: () => "en", getMessage: () => ""},
      runtime: {
        sendMessage: async msg => msg.kind === "listRecentMessages" ? recent : null,
      },
      storage: {local: {
        get: async () => history,
        set: async value => Object.assign(history, value),
      }},
    },
  });
}
function load(ctx, path) {
  vm.runInContext(fs.readFileSync(root + "/" + path, "utf8"), ctx);
}
(async () => {
  let ctx = context();
  load(ctx, "ui/summarize/summarize.js");
  await vm.runInContext("run()", ctx);
  ctx = context();
  load(ctx, "ui/compose/composeAction.js");
  await vm.runInContext("composeTab = {id: 1}; runSmartReply()", ctx);
  await vm.runInContext('document.getElementById("compose-style").value = "short"; runSmartCompose()', ctx);
  ctx = context();
  load(ctx, "ui/translate/translate.js");
  await vm.runInContext("run()", ctx);
  ctx = context();
  load(ctx, "ui/spaces/assistant.js");
  await vm.runInContext("onSend()", ctx);
  if (history.assistantHistory.at(-1).content !== "Friday [1].") {
    throw Error("Chat UI did not consume the shared answer field");
  }
  const previous = requests.length;
  ctx.browser.runtime.sendMessage = async () => ({error: "mailbox unavailable"});
  await vm.runInContext('document.getElementById("input").value = "Again"; onSend()', ctx);
  if (requests.length !== previous) throw Error("Failed mailbox read silently reached AI");

  ctx = context();
  ctx.ClawNative = {call: async (verb, args) => {
    requests.push({verb, args}); return {ok: false};
  }};
  ctx.browser.messages = {getFull: async () => ({})};
  ctx.extractPlainText = () => "Body snippet";
  ctx.hasRealAttachments = () => true;
  const background = fs.readFileSync(root + "/background.js", "utf8");
  const triage = background.match(/async function triageMessage[\s\S]*?(?=\n(?:async )?function )/);
  if (!triage) throw Error("Missing triage handler");
  vm.runInContext(triage[0], ctx);
  await vm.runInContext('triageMessage({id: 12, author: "alex", subject: "Q3"}, {})', ctx);
  process.stdout.write(JSON.stringify(requests));
})().catch(error => { console.error(error); process.exit(1); });
"""


def test_all_ui_consumers_match_the_single_manifest():
    process = subprocess.run(
        ["node", "-e", UI_DRIVER, str(HERE.resolve())],
        capture_output=True, text=True, timeout=15, cwd=HERE,
    )
    assert process.returncode == 0, process.stderr
    requests = json.loads(process.stdout)
    by_name = {tool["name"].split(".")[1]: tool for tool in MANIFEST["mcp"]["tools"]}
    assert {request["verb"] for request in requests} == set(by_name)
    assert len(requests) == 6
    for request in requests:
        args = request["args"]
        fields = {arg["name"]: arg for arg in by_name[request["verb"]]["args"]}
        assert args.keys() <= fields.keys()
        assert {name for name, arg in fields.items() if arg["required"]} <= args.keys()
        for name, value in args.items():
            assert type(value) is (bool if fields[name]["kind"] == "bool" else str)
            if "choices" in fields[name]:
                assert value in fields[name]["choices"]
    chat = next(request["args"] for request in requests if request["verb"] == "chat")
    assert json.loads(chat["context_json"]) == [
        {"sender": "alex", "subject": "Review", "date": "Friday"},
    ]
    triage = next(request["args"] for request in requests if request["verb"] == "triage")
    assert triage["sender"] == "alex" and triage["has_attachments"] is True


def test_native_bridge_preserves_invalid_args_for_host_validation():
    script = r"""
const fs = require("fs"), vm = require("vm");
const sent = [];
const listener = {addListener() {}};
const port = {
  onMessage: listener, onDisconnect: listener,
  postMessage: message => sent.push(message),
};
const ctx = vm.createContext({
  self: {}, console, setTimeout: () => 1, clearTimeout() {},
  browser: {runtime: {connectNative: () => port}},
});
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), ctx);
ctx.self.ClawNative.connect("os.claw.mail_ai");
for (const args of [false, null, [], "", {body: true}]) {
  ctx.self.ClawNative.call("summarize", args);
}
process.stdout.write(JSON.stringify(sent.map(request => request.args)));
"""
    process = subprocess.run(
        ["node", "-e", script, str(HERE / "lib" / "native.js")],
        capture_output=True, text=True, timeout=10, cwd=HERE,
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == [False, None, [], "", {"body": True}]


MAILBOX_DRIVER = r"""
const fs = require("fs"), vm = require("vm"), assert = require("assert/strict");
const {webcrypto} = require("crypto");
const {File} = require("buffer");
const profile = "00000000-0000-4000-8000-000000000001";
const stored = {mailboxProfileId: profile};
let attachmentBytes = "abc";
const headers = [
  {id: 11, headerMessageId: "draft@example.invalid", author: "Alice <alice@example.invalid>",
   recipients: ["public@example.invalid"], ccList: [], bccList: ["hidden@example.invalid"],
   subject: "Review", read: true, folder: {
     id: "account1://Drafts", accountId: "account1", specialUse: ["drafts"],
   }},
  {id: 12, headerMessageId: "other@example.invalid", author: "Bob <bob@example.invalid>",
   recipients: ["public@example.invalid"], ccList: [], bccList: [],
   subject: "Other", read: false, folder: {
     id: "account2://INBOX", accountId: "account2", specialUse: ["inbox"],
   }},
];
const body = new Map([[11, "Reviewed body"], [12, "Other account body"]]);
const attachments = new Map([[11, [{name: "evidence.txt", type: "text/plain", content: "abc"}]]]);
const calls = [];
let nextId = 20;
function account(id) {
  return {
    id, name: id, type: "imap",
    identities: [{
      id: "identity-" + id, email: id === "account1" ? "alice@example.invalid" : "bob@example.invalid",
    }],
    rootFolder: {
      id: id + "://", accountId: id, specialUse: [], subFolders: [
        {id: id + "://INBOX", name: "Inbox", accountId: id, specialUse: ["inbox"]},
        {id: id + "://Drafts", name: "Drafts", accountId: id, specialUse: ["drafts"]},
      ],
    },
  };
}
const ctx = vm.createContext({
  self: {}, console, TextEncoder, TextDecoder, btoa, atob, File, Uint8Array,
  crypto: webcrypto,
  extractPlainText: full => full.parts.map(part => part.body).join("\n"),
  browser: {
    storage: {local: {
      get: async keys => {
        if (!Array.isArray(keys)) keys = [keys];
        return Object.fromEntries(keys.filter(key => key in stored).map(key => [key, stored[key]]));
      },
      set: async values => Object.assign(stored, values),
    }},
    accounts: {
      list: async () => [account("account1"), account("account2")],
      get: async id => ["account1", "account2"].includes(id) ? account(id) : null,
    },
    messengerUtilities: {
      parseMailboxString: async value => [{email: value.match(/<([^>]+)>/)?.[1] || value}],
    },
    messages: {
      query: async query => ({messages: headers.filter(header =>
        header.folder.accountId === query.accountId
        && (!query.folderId || header.folder.id === query.folderId)
        && (!query.headerMessageId || header.headerMessageId === query.headerMessageId))}),
      abortList: async () => {},
      getFull: async id => ({
        headers: {}, parts: [{contentType: "text/plain", body: body.get(id)}],
      }),
      listAttachments: async id => (attachments.get(id) || []).map((file, index) => ({
        partName: "1." + (index + 2), name: file.name, contentType: file.type, size: file.content.length,
      })),
      getAttachmentFile: async (id, part) => {
        const file = attachments.get(id)[Number(part.split(".")[1]) - 2];
        return new File([id === 11 ? attachmentBytes : file.content], file.name, {type: file.type});
      },
      saveMessage: async (details, options) => {
        calls.push({kind: "save", details, options});
        assert.equal(options.mode, "draft");
        const native = details.identityId.slice("identity-".length);
        const header = {
          id: ++nextId, headerMessageId: "saved-" + nextId + "@example.invalid",
          author: account(native).identities[0].email,
          recipients: details.to, ccList: details.cc, bccList: details.bcc || [],
          subject: details.subject, read: true,
          folder: {id: native + "://Drafts", accountId: native, specialUse: ["drafts"]},
        };
        headers.push(header);
        body.set(header.id, details.plainTextBody);
        attachments.set(header.id, await Promise.all((details.attachments || []).map(async item => ({
          name: item.name, type: item.file.type, content: await item.file.text(),
        }))));
        return {mode: "draft", messages: [header]};
      },
      sendMessage: async (details, options) => {
        calls.push({kind: "send", details, options});
        assert.equal(options.mode, "sendNow");
        return {mode: "sendNow", headerMessageId: "sent@example.invalid", messages: []};
      },
      delete: async ids => {
        calls.push({kind: "delete", ids});
        for (const id of ids) {
          const index = headers.findIndex(header => header.id === id);
          if (index >= 0) headers.splice(index, 1);
        }
      },
    },
  },
});
vm.runInContext(fs.readFileSync(process.argv[1] + "/lib/mailbox.js", "utf8"), ctx);
(async () => {
  const mailbox = ctx.self.ClawMailbox;
  await mailbox.ready;
  const accounts = await mailbox.handle("accounts", {});
  const a = accounts.accounts[0].id, b = accounts.accounts[1].id;
  const list = await mailbox.handle("search", {account: a, query: "Review", max_results: 10});
  const id = list.messages[0].id;
  assert.equal(typeof id, "string");
  assert.notEqual(id, "11");
  const read = await mailbox.handle("read", {account: a, id});
  assert.equal(read.body, "Reviewed body");
  await assert.rejects(mailbox.handle("read", {account: b, id}), /different account/);
  const draft = await mailbox.handle("native_draft", {account: a, id});
  assert.deepEqual(Array.from(draft.draft.message.bcc), ["hidden@example.invalid"]);
  attachmentBytes = "xyz";
  const changed = await mailbox.handle("draft_send", {
    account: a, sender_account: a, id, review: draft.draft.review, confirm: true,
  });
  assert.equal(changed.conflicted, true);
  assert.equal(calls.filter(call => call.kind === "send").length, 0);
  attachmentBytes = "abc";
  const saved = await mailbox.handle("draft_save", {
    account: a, source_account: a, id,
    to: "public@example.invalid", subject: "Updated", body: "New native draft",
  });
  assert.equal(saved.sent, false);
  const save = calls.find(call => call.kind === "save");
  assert.deepEqual(Array.from(save.details.bcc), ["hidden@example.invalid"]);
  assert.equal(save.details.attachments.length, 1);
  assert.equal(await save.details.attachments[0].file.text(), "abc");
  const current = await mailbox.handle("native_draft", {account: a, id: saved.draft.id});
  const sent = await mailbox.handle("draft_send", {
    account: a, sender_account: a, id: saved.draft.id, review: current.draft.review, confirm: true,
  });
  assert.equal(sent.sent, true);
  assert.equal(sent.delivery_confirmed, false);
  const send = calls.find(call => call.kind === "send");
  assert.equal(send.details.identityId, "identity-account1");
  assert.equal(send.details.plainTextBody, "New native draft");
  assert.deepEqual(Array.from(send.details.bcc), ["hidden@example.invalid"]);
  assert.equal(send.details.attachments.length, 1);
  assert.equal(await send.details.attachments[0].file.text(), "abc");

  const baseline = await mailbox.handle("sync", {account: b});
  assert.equal(baseline.baseline, true);
  await mailbox.onNewMail(headers.find(header => header.id === 12).folder, {
    messages: [headers.find(header => header.id === 12)],
  });
  const arrivals = await mailbox.handle("sync", {account: b, cursor: baseline.cursor});
  assert.equal(arrivals.messages.length, 1);
  assert.equal(arrivals.messages[0].account, b);
  process.stdout.write("native mailbox contracts passed");
})().catch(error => {console.error(error); process.exit(1)});
"""


def test_native_mailbox_accounts_drafts_attachment_reviews_and_arrivals():
    process = subprocess.run(
        ["node", "-e", MAILBOX_DRIVER, str(HERE.resolve())],
        capture_output=True, text=True, timeout=15, cwd=HERE,
    )
    assert process.returncode == 0, process.stderr
