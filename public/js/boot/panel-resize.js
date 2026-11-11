// Drag the landscape sidebar's right edge to resize it. The handle writes
// `--panel-w-user` inline on <html>, which css/tokens.css folds into `--panel-w`,
// the one width token every consumer reads (the panel itself, the help
// tooltips); portrait redefines `--panel-w` outright, so it ignores it. And the panel's ResizeObserver in
// boot/controls.js re-runs updatePanelPan, so the brain re-centres and zooms
// out to fit the new free strip with no extra wiring. Double-click resets to
// the CSS default (a third of the viewport). The chosen width persists.
import { loadString, saveString } from "../prefs.js";

const KEY = "neurarium.panelWidth";
const MIN_W = 240;
// Always leave the brain a usable strip, e.g. 1280px wide -> at most 1024px.
const maxWidth = () => Math.max(MIN_W, Math.min(window.innerWidth * 0.8, window.innerWidth - 200));
const clamp = (w) => Math.round(Math.min(maxWidth(), Math.max(MIN_W, w)));

/**
 * Add the resize handle to the control panel.
 *
 * @param {HTMLElement} panel the #controls element
 */
export function wirePanelResize(panel) {
  const root = document.documentElement;
  const apply = (w) => root.style.setProperty("--panel-w-user", `${clamp(w)}px`);
  const stored = Number(loadString(KEY));
  if (stored > 0) apply(stored);

  const handle = document.createElement("div");
  handle.className = "panel-resize";
  handle.setAttribute("aria-hidden", "true");
  panel.append(handle);

  handle.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    handle.setPointerCapture(e.pointerId);
    const left = panel.getBoundingClientRect().left;
    root.classList.add("panel-resizing");
    const move = (ev) => apply(ev.clientX - left);
    const up = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
      handle.removeEventListener("pointercancel", up);
      root.classList.remove("panel-resizing");
      saveString(KEY, parseFloat(root.style.getPropertyValue("--panel-w-user")));
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
    handle.addEventListener("pointercancel", up);
  });
  handle.addEventListener("dblclick", () => {
    root.style.removeProperty("--panel-w-user");
    saveString(KEY, "");
  });
  // A stored width can outgrow a smaller window: re-clamp on resize.
  window.addEventListener("resize", () => {
    const w = parseFloat(root.style.getPropertyValue("--panel-w-user"));
    if (w > 0) apply(w);
  });
}
