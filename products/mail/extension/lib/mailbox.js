// Thunderbird business operations. The OS native gateway admits mailbox requests.
(function () {
  "use strict";

  const MAX_ATTACHMENT_BYTES = 16 * 1024 * 1024;
  const MAX_BODY_BYTES = 256 * 1024;
  const encoder = new TextEncoder();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let profile;
  let journalTail = Promise.resolve();

  const ready = (async () => {
    const stored = await browser.storage.local.get("mailboxProfileId");
    profile = stored.mailboxProfileId;
    if (profile === undefined) {
      profile = crypto.randomUUID();
      await browser.storage.local.set({ mailboxProfileId: profile });
    }
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(profile)) {
      throw Error("Thunderbird mailbox profile identity is corrupt");
    }
  })();

  function accountId(nativeId) {
    return `${profile}:${nativeId}`;
  }

  function nativeId(account) {
    const prefix = `${profile}:`;
    if (typeof account !== "string" || !account.startsWith(prefix)
        || !/^[A-Za-z0-9_-]{1,64}$/.test(account.slice(prefix.length))) {
      throw Error("The selected account is not in this Thunderbird profile");
    }
    return account.slice(prefix.length);
  }

  function encode(bytes) {
    let binary = "";
    for (let start = 0; start < bytes.length; start += 8192) {
      binary += String.fromCharCode(...bytes.subarray(start, start + 8192));
    }
    return btoa(binary);
  }

  function messageId(header) {
    if (!header.folder?.accountId || !header.folder.id || !header.headerMessageId) {
      throw Error("This message has no stable stored-mail reference");
    }
    const key = [accountId(header.folder.accountId), header.folder.id, header.headerMessageId];
    return encode(encoder.encode(JSON.stringify(key)))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function messageKey(value) {
    if (typeof value !== "string" || value.length > 8192) throw Error("Invalid mail reference");
    const bytes = Uint8Array.from(atob(value.replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
    const key = JSON.parse(decoder.decode(bytes));
    if (!Array.isArray(key) || key.length !== 3
        || key.some(part => typeof part !== "string" || !part || part.length > 4096)) {
      throw Error("Invalid mail reference");
    }
    nativeId(key[0]);
    return key;
  }

  async function selected(account, includeFolders = false) {
    const result = await browser.accounts.get(nativeId(account), includeFolders);
    if (!result) throw Error("The selected Thunderbird account no longer exists");
    return result;
  }

  function folders(account) {
    const result = [];
    const queue = [account.rootFolder];
    while (queue.length) {
      const folder = queue.shift();
      if (!folder || result.length >= 1024) throw Error("Mailbox folder tree exceeds its limit");
      if (folder.accountId === account.id && !folder.isUnified && !folder.isTag) result.push(folder);
      queue.push(...(folder.subFolders || []));
    }
    return result;
  }

  async function collect(first, limit) {
    let page = first;
    const messages = [];
    try {
      while (page) {
        messages.push(...page.messages.slice(0, limit - messages.length));
        if (messages.length >= limit || !page.id) break;
        page = await browser.messages.continueList(page.id);
      }
      return messages;
    } finally {
      if (page?.id) await browser.messages.abortList(page.id);
    }
  }

  async function find(account, id, draft = false) {
    const key = messageKey(id);
    if (key[0] !== account) throw Error("The message belongs to a different account");
    const header = await collect(await browser.messages.query({
      accountId: nativeId(account), folderId: key[1], headerMessageId: key[2],
    }), 2);
    if (header.length !== 1 || header[0].folder?.accountId !== nativeId(account)) {
      throw Error("The message reference is stale or ambiguous");
    }
    if (draft && !header[0].folder.specialUse.includes("drafts")) {
      throw Error("The selected message is not a stored draft");
    }
    return header[0];
  }

  function summary(header) {
    return {
      id: messageId(header),
      account: accountId(header.folder.accountId),
      header_message_id: header.headerMessageId,
      from: header.author,
      to: header.recipients,
      cc: header.ccList,
      bcc: header.bccList,
      subject: header.subject,
      date: header.date,
      unread: !header.read,
      folder: header.folder.id,
    };
  }

  async function hash(bytes) {
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
    return "sha256:" + Array.from(digest, byte => byte.toString(16).padStart(2, "0")).join("");
  }

  function bodyParts(full) {
    const pending = [full];
    const parts = [];
    let count = 0;
    while (pending.length) {
      const part = pending.shift();
      if (++count > 1000) throw Error("Message MIME tree exceeds its limit");
      if (part.body && !part.headers?.["content-disposition"]?.some(value => value.startsWith("attachment"))) {
        parts.push(part);
      }
      pending.push(...(part.parts || []));
    }
    return parts;
  }

  async function snapshot(header) {
    const full = await browser.messages.getFull(header.id);
    const parts = bodyParts(full);
    const html = parts.filter(part => part.contentType === "text/html").map(part => part.body).join("\n");
    const plain = extractPlainText(full);
    if (encoder.encode(html || plain).length > MAX_BODY_BYTES) {
      throw Error("This draft is too large for a complete Agent review");
    }
    const details = {
      from: header.author,
      to: [...header.recipients],
      cc: [...header.ccList],
      bcc: [...header.bccList],
      subject: header.subject,
      ...(html ? { body: html, isPlainText: false, deliveryFormat: "html" }
        : { plainTextBody: plain, isPlainText: true, deliveryFormat: "plaintext" }),
      attachments: [],
    };
    if (full.headers?.["reply-to"]) details.replyTo = [...full.headers["reply-to"]];
    const attachments = [];
    let total = 0;
    for (const attachment of await browser.messages.listAttachments(header.id)) {
      const file = await browser.messages.getAttachmentFile(header.id, attachment.partName);
      total += file.size;
      if (total > MAX_ATTACHMENT_BYTES || attachments.length >= 64) {
        throw Error("Draft attachments exceed the complete-review limit");
      }
      const bytes = new Uint8Array(await file.arrayBuffer());
      details.attachments.push({
        name: attachment.name,
        file: new File([bytes], attachment.name, { type: attachment.contentType }),
      });
      attachments.push({
        id: attachment.partName, name: attachment.name, content_type: attachment.contentType,
        size: bytes.length, sha256: await hash(bytes),
      });
    }
    const reviewed = {
      account: accountId(header.folder.accountId),
      id: messageId(header),
      from: details.from, to: details.to, cc: details.cc, bcc: details.bcc,
      subject: details.subject, body: html || plain, html: !!html,
      reply_to: details.replyTo || [], attachments,
    };
    return {
      details,
      review: await hash(encoder.encode(JSON.stringify(reviewed))),
      message: { ...summary(header), body: plain, html: html || null, attachments },
    };
  }

  async function identity(account, from) {
    const item = await selected(account);
    if (!item.identities.length) throw Error("This Thunderbird account has no sender identity");
    if (!from) return item.identities[0];
    const addresses = await browser.messengerUtilities.parseMailboxString(from);
    const address = addresses[0]?.email?.toLowerCase();
    const match = item.identities.find(value => value.email.toLowerCase() === address);
    if (!match) throw Error("The reviewed draft sender is not an identity of the selected sender account");
    return match;
  }

  function outgoing(args, sender) {
    return {
      identityId: sender.id,
      to: args.to.split(",").map(value => value.trim()).filter(Boolean),
      cc: args.cc ? args.cc.split(",").map(value => value.trim()).filter(Boolean) : [],
      subject: args.subject,
      plainTextBody: args.body,
      isPlainText: true,
      deliveryFormat: "plaintext",
    };
  }

  async function removeUnchanged(account, header, captured) {
    const current = await find(account, messageId(header), true);
    if ((await snapshot(current)).review !== captured.review) return false;
    await browser.messages.delete([current.id], { deletePermanently: true });
    return true;
  }

  async function send(args) {
    const sender = await identity(args.account);
    const result = await browser.messages.sendMessage(outgoing(args, sender), { mode: "sendNow" });
    return {
      account: args.account, sent: true, mode: result.mode,
      id: result.messages?.length ? messageId(result.messages[0]) : null,
      header_message_id: result.headerMessageId || null, delivery_confirmed: false,
    };
  }

  async function saveDraft(args) {
    let previous;
    let captured;
    if (args.id) {
      if (!args.source_account || messageKey(args.id)[0] !== args.source_account) {
        throw Error("Draft replacement requires its explicit source account");
      }
      previous = await find(args.source_account, args.id, true);
      captured = await snapshot(previous);
    }
    const sender = await identity(args.account);
    const details = { ...(captured?.details || {}), ...outgoing(args, sender) };
    delete details.body;
    delete details.from;
    const result = await browser.messages.saveMessage(details, { mode: "draft" });
    const header = result.messages[0];
    if (!header) throw Error("Thunderbird saved no addressable draft");
    const response = {
      account: args.account, saved: true, sent: false,
      draft: { id: messageId(header), account: accountId(header.folder.accountId) },
    };
    if (previous) {
      try {
        response.replaced = await removeUnchanged(args.source_account, previous, captured);
      } catch (_) {
        response.replaced = false;
      }
      if (!response.replaced) response.previous_retained = true;
    }
    return response;
  }

  async function sendDraft(args) {
    if (args.confirm !== true) throw Error("Sending a draft requires explicit confirmation");
    const header = await find(args.account, args.id, true);
    const captured = await snapshot(header);
    if (captured.review !== args.review) {
      return { account: args.account, error: "Draft changed; read and review it again", conflicted: true };
    }
    const sender = await identity(args.sender_account, captured.details.from);
    const details = { ...captured.details, identityId: sender.id };
    const result = await browser.messages.sendMessage(details, { mode: "sendNow" });
    const response = {
      account: args.account, sender_account: args.sender_account, sent: true,
      draft_id: args.id, mode: result.mode,
      id: result.messages?.length ? messageId(result.messages[0]) : null,
      header_message_id: result.headerMessageId || null, delivery_confirmed: false,
    };
    try {
      response.draft_removed = await removeUnchanged(args.account, header, captured);
    } catch (_) {
      response.draft_removed = false;
    }
    if (!response.draft_removed) response.draft_retained = true;
    return response;
  }

  async function onNewMail(folder, first) {
    if (!folder.accountId || !folder.specialUse.includes("inbox")) return;
    journalTail = journalTail.then(async () => {
      await ready;
      const stored = await browser.storage.local.get("mailboxJournal");
      const journal = stored.mailboxJournal || { sequence: 0, items: [] };
      for (const header of await collect(first, 500)) {
        journal.items.push({
          sequence: ++journal.sequence, account: accountId(folder.accountId), id: messageId(header),
        });
      }
      journal.items = journal.items.slice(-500);
      await browser.storage.local.set({ mailboxJournal: journal });
    });
    try {
      await journalTail;
    } catch (_) {
      await browser.storage.local.set({ mailboxJournalFailed: true });
      console.error("[claw-mail] new-mail journal failed");
    }
  }

  async function sync(args) {
    await journalTail.catch(() => {});
    const stored = await browser.storage.local.get(["mailboxJournal", "mailboxJournalFailed"]);
    if (stored.mailboxJournalFailed) throw Error("Thunderbird new-mail journal needs manual repair");
    const journal = stored.mailboxJournal || { sequence: 0, items: [] };
    if (args.reset || args.cursor === undefined) {
      return { account: args.account, cursor: journal.sequence, messages: [], baseline: true };
    }
    if (args.cursor > journal.sequence
        || (journal.items.length && args.cursor < journal.items[0].sequence - 1)) {
      return { account: args.account, error: "Thunderbird mailbox continuation expired; use --reset", reset_required: true };
    }
    return {
      account: args.account, cursor: journal.sequence,
      messages: journal.items.filter(item => item.account === args.account && item.sequence > args.cursor),
      baseline: false,
    };
  }

  async function handle(verb, args) {
    await ready;
    if (verb === "accounts") {
      const items = await browser.accounts.list(false);
      return {
        accounts: items.map(item => ({
          id: accountId(item.id), name: item.name, type: item.type,
          identities: item.identities.map(value => ({ id: value.id, name: value.name, email: value.email })),
          can_send: item.identities.length > 0,
        })),
        backend: "thunderbird",
      };
    }
    const item = await selected(args.account, true);
    if (verb === "folders") {
      return { account: args.account, folders: folders(item).map(folder => ({
        id: folder.id, name: folder.name, special_use: folder.specialUse,
      })) };
    }
    if (verb === "sync") return sync(args);
    if (verb === "send") return send(args);
    if (verb === "draft_save") return saveDraft(args);
    if (verb === "draft_send") return sendDraft(args);
    if (verb === "list" || verb === "search") {
      const available = folders(item);
      const folder = args.folder ? available.find(value => value.id === args.folder)
        : verb === "list" ? available.find(value => value.specialUse.includes("inbox")) : undefined;
      if (verb === "list" && !folder) throw Error("This account has no selected inbox folder");
      if (args.folder && !folder) throw Error("The selected folder is not in this account");
      const query = { accountId: item.id };
      if (folder) query.folderId = folder.id;
      if (verb === "search") query.fullText = args.query;
      if (args.unread) query.unread = true;
      const messages = await collect(await browser.messages.query(query), args.max_results || 10);
      if (messages.some(header => header.folder?.accountId !== item.id)) {
        throw Error("Thunderbird returned a message from another account");
      }
      return { account: args.account, messages: messages.map(summary) };
    }
    const header = await find(args.account, args.id, verb === "native_draft");
    if (verb === "attachment_download") {
      const attachment = (await browser.messages.listAttachments(header.id))
        .find(value => value.partName === args.attachment);
      if (!attachment) throw Error("The native MIME attachment was not found");
      const file = await browser.messages.getAttachmentFile(header.id, attachment.partName);
      if (file.size > args.max_bytes || file.size > MAX_ATTACHMENT_BYTES) throw Error("Attachment exceeds its byte limit");
      return {
        account: args.account, id: args.id, attachment: args.attachment,
        data: encode(new Uint8Array(await file.arrayBuffer())),
      };
    }
    if (verb === "native_draft") {
      const captured = await snapshot(header);
      return {
        account: args.account,
        draft: { id: args.id, review: captured.review, message: captured.message },
      };
    }
    if (verb === "read") {
      const full = await browser.messages.getFull(header.id);
      const plain = extractPlainText(full);
      const bytes = encoder.encode(plain);
      return {
        account: args.account, ...summary(header),
        body: new TextDecoder("utf-8").decode(bytes.subarray(0, MAX_BODY_BYTES)),
        truncated: bytes.length > MAX_BODY_BYTES,
        attachments: (await browser.messages.listAttachments(header.id)).map(value => ({
          id: value.partName, name: value.name, size: value.size, content_type: value.contentType,
        })),
      };
    }
    throw Error("Unknown native Mail operation");
  }

  self.ClawMailbox = { ready, handle, onNewMail };
})();
