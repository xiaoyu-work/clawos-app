ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  const $ = (selector) => document.querySelector(selector);
  const editor = $("#editor");
  const has = (command) => Boolean(ClawApp.tool(app, command));
  let boundPath = "";
  let baseline = "";
  let revision = 0;
  let documentId = 0;
  let busy = false;
  let uncertain = false;
  let conflict = false;
  let pendingSave = null;
  let proposal = null;
  ui.showApp(app);

  function dirty() { return editor.value !== baseline; }
  function checked(value) {
    ui.output($("#raw"), value);
    if (value && value.error) throw new Error(String(value.error));
    return value;
  }
  function call(command, args) {
    const tool = ClawApp.tool(app, command);
    if (!tool) throw new Error(`This entry does not declare ${command}.`);
    return ClawApp.call(tool.name, args);
  }
  function matches() {
    const find = $("#find").value;
    return find ? editor.value.split(find).length - 1 : 0;
  }
  function update() {
    $("#bound-path").textContent = boundPath || "Untitled buffer";
    $("#state").textContent = uncertain ? "Save outcome unknown - check disk" : conflict ? "Saved file changed" :
      dirty() ? "Unsaved edits" : boundPath ? "No local unsaved edits" : "New buffer";
    $("#counts").textContent = `${editor.value.length} characters - ${editor.value.split("\n").length} lines`;
    $("#matches").textContent = $("#find").value ? `${matches()} matches` : "";
    $("#save").disabled = busy || !boundPath || uncertain || conflict || !has("write");
    $("#save-as").disabled = busy || uncertain || !has("write");
    $("#reload").disabled = busy || !boundPath || !has("read");
    $("#check").disabled = busy || (!boundPath && !pendingSave) || !has("read");
    for (const button of $("#ai-actions").querySelectorAll("button")) button.disabled = busy || !boundPath || dirty() || uncertain || conflict;
    $("#accept-proposal").disabled = busy || !proposal || proposal.documentId !== documentId ||
      proposal.revision !== revision || proposal.path !== boundPath || uncertain || conflict;
    $("#proposal-state").textContent = !proposal ? "" : proposal.revision !== revision || proposal.documentId !== documentId ?
      "The buffer changed after this proposal was requested. Discard it and request a new proposal." :
      "Accepting changes only this buffer. A separate reviewed save is still required.";
    $("#replace-next").disabled = busy || !matches();
    $("#replace-all").disabled = busy || !matches();
  }
  async function perform(action, render) {
    if (busy) return;
    busy = true;
    const controls = Array.from(document.querySelectorAll("button, input, textarea")).filter((control) => !control.disabled);
    controls.forEach((control) => { control.disabled = true; });
    await ui.run(null, async () => checked(await action()), render, $("#notice"));
    busy = false;
    controls.forEach((control) => { control.disabled = false; });
    update();
  }
  function discardThen(action) {
    if (busy) return;
    if (!dirty()) { action(); return; }
    const dialog = ui.node("dialog");
    dialog.append(ui.node("h2", "Discard unsaved buffer changes?"),
      ui.node("p", "This only discards the Web buffer. It does not change any saved file."));
    const buttons = ui.node("div", null, { class: "toolbar" });
    const cancel = ui.node("button", "Keep editing", { type: "button" });
    const discard = ui.node("button", "Discard buffer changes", { type: "button", class: "danger" });
    cancel.onclick = () => dialog.close();
    discard.onclick = () => { dialog.close(); action(); };
    buttons.append(cancel, discard);
    dialog.append(buttons);
    dialog.addEventListener("close", () => dialog.remove());
    document.body.append(dialog);
    dialog.showModal();
  }
  function readFile(path) {
    const id = documentId;
    void perform(() => call("read", { path }), (value) => {
      if (id !== documentId) return;
      if (!value || typeof value.content !== "string") throw new Error("No UTF-8 file content was returned.");
      boundPath = typeof value.path === "string" ? value.path : path;
      $("#path").value = boundPath;
      baseline = value.content;
      editor.value = value.content;
      revision++;
      documentId++;
      uncertain = false;
      conflict = false;
      pendingSave = null;
      proposal = null;
      $("#proposal").hidden = true;
      $("#analysis").textContent = "";
      $("#outcome").textContent = "File loaded into the buffer.";
    });
  }
  function saveDialog(saveAs) {
    const snapshot = editor.value;
    const id = documentId;
    const path = boundPath;
    let targetPath = path;
    ui.command(app, "write", { path: saveAs ? "" : path, content: snapshot }, (value) => {
      checked(value);
      if (id !== documentId) return;
      if (value.written !== true) throw new Error("The write was not confirmed. Check the saved file before another write.");
      const target = targetPath;
      boundPath = target;
      $("#path").value = target;
      baseline = snapshot;
      uncertain = false;
      conflict = false;
      pendingSave = null;
      $("#outcome").textContent = `Backend confirmed a write to ${target}.`;
      update();
    }, {
      title: saveAs ? "Create or overwrite a file" : "Review complete file replacement",
      submitLabel: saveAs ? "Create / overwrite file" : "Save complete replacement",
      description: "Writes the entire buffer, including an empty document. Existing contents at the exact path are replaced. There is no atomic compare-and-save contract; external changes can race this write. A timeout is not permission to retry.",
      fields: { path: { label: "Exact authorized destination", readOnly: !saveAs, type: "text" },
        content: { label: "Complete contents to save", type: "textarea", readOnly: true, rows: 10, allowEmpty: true, includeEmpty: true } },
    });
    const form = document.querySelector("dialog form");
    form.addEventListener("submit", () => {
      uncertain = true;
      targetPath = form.querySelector('[name="path"]').value;
      pendingSave = { path: targetPath, content: snapshot, documentId: id };
      $("#outcome").textContent = `Save requested to ${pendingSave.path}. If unconfirmed, check that exact destination before another write.`;
      update();
    });
  }
  function reviewSave() {
    if (!boundPath || busy || uncertain || conflict) return;
    const path = boundPath;
    const id = documentId;
    void perform(() => call("read", { path }), (value) => {
      if (id !== documentId) return;
      if (typeof value.content !== "string") throw new Error("Cannot compare the current saved file.");
      if (value.content !== baseline) {
        conflict = true;
        $("#outcome").textContent = "The saved file differs from the last read. Your buffer is preserved. Reload explicitly or Save as a different file.";
        return;
      }
      saveDialog(false);
    });
  }
  function findNext() {
    const find = $("#find").value;
    if (!find) return;
    let index = editor.value.indexOf(find, editor.selectionEnd);
    if (index < 0) index = editor.value.indexOf(find);
    if (index < 0) { $("#matches").textContent = "No matches"; return; }
    editor.focus();
    editor.setSelectionRange(index, index + find.length);
    $("#matches").textContent = `${matches()} matches - selected at character ${index + 1}`;
  }
  function edited() { revision++; update(); }
  editor.oninput = edited;
  $("#find").oninput = update;
  $("#file-form").onsubmit = (event) => {
    event.preventDefault();
    if (!$("#file-form").reportValidity()) return;
    const path = $("#path").value;
    discardThen(() => readFile(path));
  };
  $("#new").onclick = () => discardThen(() => {
    editor.value = "";
    baseline = "";
    boundPath = "";
    $("#path").value = "";
    uncertain = false;
    conflict = false;
    pendingSave = null;
    proposal = null;
    documentId++;
    revision++;
    $("#proposal").hidden = true;
    $("#analysis").textContent = "";
    $("#outcome").textContent = "New unsaved buffer. Use Save as to choose a destination.";
    update();
  });
  $("#reload").onclick = () => discardThen(() => readFile(boundPath));
  $("#save").onclick = reviewSave;
  $("#save-as").onclick = () => { if (!busy && !uncertain && has("write")) saveDialog(true); };
  $("#check").onclick = () => {
    const id = documentId;
    const pending = pendingSave;
    const path = pending ? pending.path : boundPath;
    void perform(() => call("read", { path }), (value) => {
      if (id !== documentId) return;
      if (typeof value.content !== "string") throw new Error("No saved-file text was returned.");
      if (pending && pending.path !== boundPath) {
        if (value.content !== pending.content) {
          $("#outcome").textContent = `The requested destination ${path} does not match the attempted save. The save remains unconfirmed; your buffer is preserved.`;
          return;
        }
        boundPath = typeof value.path === "string" ? value.path : path;
        $("#path").value = boundPath;
        baseline = pending.content;
        uncertain = false;
        conflict = false;
        pendingSave = null;
        $("#outcome").textContent = `The requested destination ${boundPath} now matches the attempted save.`;
        return;
      }
      if (value.content === editor.value) {
        baseline = value.content;
        uncertain = false;
        conflict = false;
        pendingSave = null;
        $("#outcome").textContent = "The saved file matches this buffer at the time of this read.";
      } else if (value.content === baseline) {
        uncertain = false;
        conflict = false;
        pendingSave = null;
        $("#outcome").textContent = "The saved file still matches the previous baseline; your edits remain unsaved.";
      } else {
        conflict = true;
        uncertain = false;
        pendingSave = null;
        $("#outcome").textContent = "The saved file differs from both the buffer and its baseline. Nothing was overwritten.";
      }
    });
  };
  $("#find-form").onsubmit = (event) => { event.preventDefault(); if (!busy) findNext(); };
  $("#replace-next").onclick = () => {
    if (busy || !$("#find").value) return;
    const find = $("#find").value;
    if (editor.value.slice(editor.selectionStart, editor.selectionEnd) !== find) findNext();
    if (editor.value.slice(editor.selectionStart, editor.selectionEnd) !== find) return;
    editor.setRangeText($("#replacement").value, editor.selectionStart, editor.selectionEnd, "end");
    edited();
  };
  $("#replace-all").onclick = () => {
    if (busy || !$("#find").value) return;
    const count = matches();
    editor.value = editor.value.split($("#find").value).join($("#replacement").value);
    edited();
    $("#outcome").textContent = `${count} replacements in the buffer only. Review before saving.`;
  };
  for (const [command, label] of [["summarize", "Summarize saved file"], ["explain", "Explain saved file"], ["rewrite", "Propose a rewrite"]]) {
    if (!has(command)) continue;
    const button = ui.node("button", label, { type: "button" });
    button.onclick = () => {
      if (busy || dirty() || uncertain || conflict || !boundPath) return;
      const source = { path: boundPath, revision, documentId };
      ui.command(app, command, { path: boundPath }, (value) => {
        checked(value);
        if (source.documentId !== documentId || source.revision !== revision || source.path !== boundPath) return;
        const text = command === "summarize" ? value.summary : value.text;
        if (typeof text !== "string") throw new Error("The AI service returned no document text.");
        if (command === "rewrite") {
          proposal = { ...source, text };
          $("#proposal-text").value = text;
          $("#proposal").hidden = false;
        } else $("#analysis").textContent = text;
        $("#outcome").textContent = "AI response received for the saved file. No file was written.";
        update();
      }, {
        title: label, submitLabel: "Request AI assistance",
        description: "Reads this saved file again through the SDK AI gate. It does not receive unsaved buffer content, and may use your App AI budget. Rewrite returns a proposal only.",
        fields: { path: { readOnly: true }, instruction: { label: "Rewrite instructions", rows: 5 } },
      });
    };
    $("#ai-actions").append(button);
  }
  $("#accept-proposal").onclick = () => {
    if (!proposal || busy || proposal.documentId !== documentId || proposal.revision !== revision ||
        proposal.path !== boundPath || uncertain || conflict) return;
    editor.value = proposal.text;
    revision++;
    proposal = null;
    $("#proposal").hidden = true;
    $("#outcome").textContent = "Proposal copied to the unsaved buffer. Review and save separately.";
    update();
  };
  $("#discard-proposal").onclick = () => { proposal = null; $("#proposal").hidden = true; update(); };
  $("#desktop").hidden = !has("open");
  $("#desktop").onclick = () => ui.command(app, "open", boundPath ? { path: boundPath } : {}, (value) => {
    checked(value);
    $("#outcome").textContent = value.opened === true ? "Native editor activation reported. This Web buffer is not transferred." : "Native activation was not confirmed.";
  }, { title: "Open the native editor", submitLabel: "Open native window",
    description: "Explicitly activates this product's native editor through the OS. Unsaved Web content is not shared or saved.",
    fields: { path: { type: "text" } } });
  update();
});
