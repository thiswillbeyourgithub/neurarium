// Stamp the app version into every [data-app-version] slot (single source:
// window.__APP_VERSION__ from version.js), so a new display spot is markup-only, no
// second lookup. Shared by both pages: the viewer (js/main.js: panel header + loading
// overlay title) and the drugs map (js/drugs-map-main.js: its header).

export function stampVersion() {
  if (!window.__APP_VERSION__) return;
  for (const el of document.querySelectorAll("[data-app-version]")) {
    el.textContent = `v${window.__APP_VERSION__}`;
  }
}
