ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  ui.showApp(app);
  if (app.id === "panel-calendar") {
    panelCalendar(app, ui);
    return;
  }
  let selectedDay = new Date();
  let month = new Date(selectedDay.getFullYear(), selectedDay.getMonth(), 1);
  let events = [];
  let selectedEvent = null;
  let generation = 0;
  const notice = document.querySelector("#notice");
  const provider = document.querySelector("#provider");
  const dateTime = (value) => {
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return "";
    const pad = (number) => String(number).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  };
  const timestamp = (value) => {
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) throw new Error("Choose a valid date and time.");
    return date.toISOString();
  };
  const when = (value) => value ? new Date(value).toLocaleString() : "Not specified";
  const fields = {
    provider: { label: "Calendar", hidden: true },
    id: { label: "Event", hidden: true },
    title: { label: "Title", type: "text", placeholder: "Event title" },
    start: { label: "Starts", type: "datetime-local", format: dateTime, parse: timestamp },
    end: { label: "Ends", type: "datetime-local", format: dateTime, parse: timestamp },
    description: { label: "Description", type: "textarea", rows: 4, includeEmpty: true },
    location: { label: "Location", type: "text", includeEmpty: true },
    attendees: { label: "Invite people", type: "text", placeholder: "alice@example.com, bob@example.com" },
    response: { label: "Your response" },
    confirm: { label: "I confirm this invitation or response will be sent to the provider." },
  };
  const defaults = () => {
    const start = new Date(selectedDay.getFullYear(), selectedDay.getMonth(), selectedDay.getDate(), 9);
    return { provider: provider.value, start: start.toISOString(),
      end: new Date(start.getTime() + 3600000).toISOString() };
  };
  function edit(command, title, values, submitLabel) {
    ui.command(app, command, values, async () => { await load(); }, { title, submitLabel, fields });
  }
  function dayEvents(date) {
    const start = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const end = new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1);
    return events.filter((item) => {
      const begins = new Date(item.start);
      const finishes = item.end ? new Date(item.end) : begins;
      return begins < end && (finishes > start || begins >= start);
    });
  }
  function details(event) {
    selectedEvent = event.id;
    const target = document.querySelector("#details");
    const description = ui.node("dl", null, { class: "detail-grid" });
    for (const [label, value] of [["Calendar", provider.value], ["Starts", when(event.start)],
      ["Ends", when(event.end)], ["Location", event.location || "Not specified"]]) {
      description.append(ui.node("dt", label), ui.node("dd", value));
    }
    const actions = ui.node("div", null, { class: "toolbar" });
    const values = { ...event, provider: provider.value };
    const add = (command, label, run) => {
      if (!ClawApp.tool(app, command)) return;
      const button = ui.node("button", label);
      button.onclick = run;
      actions.append(button);
    };
    add("update", "Edit event", () => edit("update", "Edit event", values, "Save changes"));
    add("delete", "Delete event", () => ui.command(app, "delete", values, async () => {
      selectedEvent = null;
      ui.replace(target, [ui.node("p", "Event deleted.", { class: "muted" })]);
      await load();
    }, { title: "Delete event?", description: `Delete "${event.title || event.id}" from ${provider.value}.`,
      submitLabel: "Delete event", fields }));
    if (provider.value !== "local") {
      add("respond", "Respond to invitation", () => edit("respond", "Respond to invitation", values, "Send response"));
    }
    const guests = ui.node("div", null, { class: "stack" });
    for (const attendee of event.attendees || []) guests.append(ui.node("p",
      `${attendee.email || attendee} - ${attendee.response || "Awaiting response"}`, { class: "small" }));
    ui.replace(target, [ui.node("h3", event.title || "(Untitled event)"), description,
      ui.node("p", event.description || "No description.", { class: "prose" }), guests, actions]);
  }
  function agenda() {
    document.querySelector("#day-title").textContent = selectedDay.toLocaleDateString(undefined,
      { weekday: "long", month: "long", day: "numeric" });
    const values = dayEvents(selectedDay);
    ui.replace(document.querySelector("#agenda"), values.length ? values.map((event) => {
      const button = ui.node("button", null, { class: "stack" });
      button.append(ui.node("strong", event.title || "(Untitled event)"),
        ui.node("span", `${when(event.start)}${event.location ? ` - ${event.location}` : ""}`, { class: "muted small" }));
      button.onclick = () => details(event);
      return button;
    }) : [ui.node("p", "No events on this day.", { class: "muted" })]);
  }
  function render() {
    document.querySelector("#month").textContent = month.toLocaleDateString(undefined, { year: "numeric", month: "long" });
    const first = new Date(month.getFullYear(), month.getMonth(), 1);
    const start = new Date(first); start.setDate(1 - first.getDay());
    const cells = [];
    for (let index = 0; index < 42; index++) {
      const date = new Date(start); date.setDate(start.getDate() + index);
      const cell = ui.node("div", null, { class: "day" });
      if (date.toDateString() === new Date().toDateString()) cell.classList.add("today");
      if (date.getMonth() !== month.getMonth()) cell.classList.add("outside");
      if (date.toDateString() === selectedDay.toDateString()) cell.classList.add("selected");
      const day = ui.node("button", date.getDate(), { class: "day-number",
        "aria-label": date.toLocaleDateString() });
      day.onclick = () => { selectedDay = date; render(); };
      cell.append(day);
      for (const event of dayEvents(date)) {
        const button = ui.node("button", event.title || "(Untitled event)");
        button.onclick = () => { selectedDay = date; render(); details(event); };
        cell.append(button);
      }
      cells.push(cell);
    }
    ui.replace(document.querySelector("#calendar"), cells);
    agenda();
  }
  function load() {
    const request = ++generation;
    events = [];
    render();
    if (!ClawApp.tool(app, "list")) {
      notice.textContent = "This entry does not declare the Calendar event-list tool.";
      return;
    }
    return ui.run(document.querySelector("#refresh"), () => ClawApp.call("list", {
      provider: provider.value,
      from: new Date(month.getFullYear(), month.getMonth(), 1).toISOString(),
      to: new Date(month.getFullYear(), month.getMonth() + 1, 1).toISOString(),
    }), (result) => {
      if (request !== generation) return;
      events = ui.rows(result).sort((a, b) => new Date(a.start) - new Date(b.start));
      render();
      if (selectedEvent) {
        const event = events.find((item) => item.id === selectedEvent);
        if (event) details(event);
        else {
          selectedEvent = null;
          ui.replace(document.querySelector("#details"), [ui.node("p", "This event is no longer in the selected range.", { class: "muted" })]);
        }
      }
    }, notice);
  }
  function move(offset) {
    month = new Date(month.getFullYear(), month.getMonth() + offset, 1);
    selectedDay = new Date(month);
    void load();
  }
  document.querySelector("#previous").onclick = () => move(-1);
  document.querySelector("#next").onclick = () => move(1);
  document.querySelector("#today").onclick = () => {
    selectedDay = new Date();
    month = new Date(selectedDay.getFullYear(), selectedDay.getMonth(), 1);
    void load();
  };
  document.querySelector("#refresh").onclick = load;
  provider.onchange = () => {
    selectedEvent = null;
    ui.replace(document.querySelector("#details"), [ui.node("p", "Select an event to inspect it.", { class: "muted" })]);
    void load();
  };
  document.querySelector("#create").disabled = !ClawApp.tool(app, "create");
  document.querySelector("#create").onclick = () => edit("create", "New event", defaults(), "Create event");
  if (ClawApp.tool(app, "invite")) {
    const invite = ui.node("button", "Invite people");
    invite.onclick = () => {
      if (provider.value === "local") {
        notice.textContent = "Choose Google or Outlook to send invitations. Local events do not send mail.";
        return;
      }
      edit("invite", "Schedule a meeting", defaults(), "Create and send invitations");
    };
    document.querySelector("#create").after(invite);
  }
  const weekdays = Array.from({ length: 7 }, (_, index) => ui.node("span",
    new Date(2026, 10, 1 + index).toLocaleDateString(undefined, { weekday: "short" })));
  ui.replace(document.querySelector("#weekdays"), weekdays);
  ui.allTools(document.querySelector("#more"), app, (value) => ui.output(document.querySelector("#details"), value), defaults);
  void load();
});

function panelCalendar(app, ui) {
  "use strict";
  const $ = (id) => document.getElementById(id);
  let selected = new Date();
  let month = new Date(selected.getFullYear(), selected.getMonth(), 1);
  let generation = 0;
  const key = (date) => `${String(date.getFullYear()).padStart(4, "0")}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  const when = (value) => {
    if (!value) return "Not specified";
    const date = new Date(value);
    return Number.isFinite(date.getTime()) ? date.toLocaleString() : value;
  };
  $("provider").hidden = true;
  $("create").hidden = true;
  $("more").hidden = true;
  document.querySelector("[data-app-label]").textContent = "Read-only local Calendar agenda. Account calendars and event editing belong to the separate Calendar entry.";
  ui.replace($("weekdays"), Array.from({ length: 7 }, (_, index) => ui.node("span",
    new Date(2026, 10, 1 + index).toLocaleDateString(undefined, { weekday: "short" }))));

  function renderMonth() {
    $("month").textContent = month.toLocaleDateString(undefined, { month: "long", year: "numeric" });
    $("day-title").textContent = selected.toLocaleDateString(undefined,
      { weekday: "long", month: "long", day: "numeric", year: "numeric" });
    const first = new Date(month);
    first.setDate(1 - first.getDay());
    ui.replace($("calendar"), Array.from({ length: 42 }, (_, index) => {
      const date = new Date(first); date.setDate(first.getDate() + index);
      const cell = ui.node("div", null, {
        class: `day${key(date) === key(selected) ? " selected" : ""}${date.getMonth() !== month.getMonth() ? " outside" : ""}${key(date) === key(new Date()) ? " today" : ""}`,
      });
      const button = ui.node("button", date.getDate(), { type: "button", class: "day-number",
        "aria-label": date.toLocaleDateString(), "aria-pressed": String(key(date) === key(selected)) });
      button.onclick = () => { selected = date; void load(); };
      cell.append(button);
      return cell;
    }));
  }
  function details(event) {
    const values = ui.node("dl", null, { class: "detail-grid" });
    for (const [label, value] of [["Starts", when(event.start)], ["Ends", when(event.end)],
      ["Location", event.location || "Not specified"]]) {
      values.append(ui.node("dt", label), ui.node("dd", value));
    }
    ui.replace($("details"), [ui.node("h3", event.title || "(Untitled event)"), values]);
  }
  async function load() {
    const request = ++generation;
    renderMonth();
    $("refresh").disabled = true;
    $("notice").textContent = "";
    ui.replace($("agenda"), [ui.node("p", "Loading the selected day's agenda…", { class: "muted" })]);
    ui.replace($("details"), [ui.node("p", "Select an event to inspect it.", { class: "muted" })]);
    try {
      if (!ClawApp.tool(app, "panel-calendar.day")) throw new Error("This App does not declare the day-agenda service.");
      const result = await ClawApp.call("panel-calendar.day", { date: key(selected) });
      if (request !== generation) return;
      if (!Array.isArray(result.events)) throw new Error("The Calendar service returned an invalid agenda.");
      ui.replace($("agenda"), result.events.length ? result.events.map((event) => {
        const button = ui.node("button", null, { type: "button", class: "stack" });
        button.append(ui.node("strong", event.title || "(Untitled event)"),
          ui.node("span", `${when(event.start)}${event.location ? ` — ${event.location}` : ""}`, { class: "small muted" }));
        button.onclick = () => details(event);
        return button;
      }) : [ui.node("p", "No events on this day.", { class: "muted" })]);
    } catch (error) {
      if (request !== generation) return;
      $("notice").textContent = `Calendar unavailable: ${error.message}`;
      ui.replace($("agenda"), [ui.node("p", "Agenda unavailable. The service error above may indicate denied access or an unavailable OS service.", { class: "notice" })]);
    } finally {
      if (request === generation) $("refresh").disabled = false;
    }
  }
  function move(offset) {
    month = new Date(month.getFullYear(), month.getMonth() + offset, 1);
    selected = new Date(month);
    void load();
  }
  $("previous").onclick = () => move(-1);
  $("next").onclick = () => move(1);
  $("today").onclick = () => {
    selected = new Date();
    month = new Date(selected.getFullYear(), selected.getMonth(), 1);
    void load();
  };
  $("refresh").onclick = load;
  void load();
}
