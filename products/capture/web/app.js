ClawApp.ready.then((app) => {
  "use strict";
  const ui = ClawUi;
  ui.showApp(app);
  function result(value) {
    const target = document.querySelector("#result");
    ui.output(target, value);
    for (const item of value && value.content || []) {
      if (item.type === "image" && typeof item.data === "string" && ["image/png", "image/jpeg"].includes(item.mimeType)) {
        const image = ui.node("img", null, { alt: "App capture result", src: `data:${item.mimeType};base64,${item.data}` });
        image.style.maxWidth = "100%"; target.append(image);
      }
    }
  }
  ui.actions(document.querySelector("#actions"), app, [{ command: "capture", label: "Capture screenshot" }], result,
    () => ({ interactive: true, modal: true }));
  ui.allTools(document.querySelector("#more"), app, result);
});
