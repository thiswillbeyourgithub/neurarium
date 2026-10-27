// The panel header's two view toggles: day/night (#toggle-theme) and the
// panel-only "reading" mode (#toggle-3d). Both labels name the state a click
// would GIVE you, so they are re-announced on every flip.

import { loadFlag, saveFlag } from "../prefs.js";

const { t } = window.__I18N__;
const NO3D_KEY = "neurarium.no3d";

/**
 * @returns {{no3dOn: () => boolean, setNo3d: (on: boolean, opts?: {persist?: boolean}) => void}}
 */
export function wireHeaderToggles({ theme, expandPanel, invalidate, intro, urlState }) {
  wireThemeButton(theme);

  // Panel-only ("reading") mode: the stylesheet hides the canvas + label overlay
  // and lets the expanded panel fill the viewport, for reading the sourced texts
  // without a brain behind them. Persisted, since it is a lasting preference about
  // how the site is used, not a per-visit action.
  const toggle3d = document.getElementById("toggle-3d");
  const no3dOn = () => document.body.classList.contains("no-3d");
  // `aria-pressed` alone left the tooltip, the accessible name AND the search row
  // (which reads a control's title, see commandRows) offering to hide a 3D model
  // that was already hidden.
  const label3d = () => {
    const label = t(no3dOn() ? "panel.show3d" : "panel.no3d");
    toggle3d?.setAttribute("title", label);
    toggle3d?.setAttribute("aria-label", label);
  };
  label3d();
  // `persist` is what separates the two ways in: the header button states a lasting
  // preference, while a view that merely wants the room (the Data browser) borrows
  // the mode for this visit and must not rewrite what the visitor chose.
  const setNo3d = (on, { persist = true } = {}) => {
    if (on === no3dOn()) return;
    // With no brain behind it a collapsed panel would leave a blank viewport, so
    // entering the reading mode maximizes the panel rather than hiding everything.
    if (on) expandPanel();
    document.body.classList.toggle("no-3d", on);
    toggle3d?.setAttribute("aria-pressed", String(on));
    label3d();
    if (persist) saveFlag(NO3D_KEY, on);
    if (!on) invalidate(); // the scene is back and holds a stale frame; repaint it
    else intro.cancel(); // nothing renders while hidden, so don't resume mid-pose
    urlState.sync(); // whether the brain is shown is part of the shareable link
  };
  toggle3d?.addEventListener("click", () => setNo3d(!no3dOn()));
  // The mirror of setNo3d's expandPanel: folding the panel back down leaves the
  // reading mode, since a collapsed panel with no brain behind it is a bare black
  // viewport. This listener is added after wireControls' own (it runs second), so
  // the body's `hidden` already reflects the click; a collapse is read off the DOM.
  document.getElementById("controls-toggle")?.addEventListener("click", () => {
    if (document.getElementById("controls-body")?.hidden && no3dOn()) setNo3d(false);
  });
  // The persisted preference first, so the link registered below (which may have been
  // parked since the hash was applied) is the one that wins: `#panel=0` must be able to
  // force the brain back on for a visitor whose stored preference is the reading mode.
  if (loadFlag(NO3D_KEY, false)) setNo3d(true);
  // `#panel=1` opens straight into the reading mode, `#panel=0` forces the brain back
  // on; a link that says nothing about it leaves the persisted preference alone.
  urlState.register("panel", {
    read: () => (no3dOn() ? "1" : null),
    write: (v) => setNo3d(v !== "0"),
  });

  return { no3dOn, setNo3d };
}

/**
 * Day/night (#toggle-theme): a pure viewing preference, so it owns no app state at all.
 * js/theme.js persists the choice (and, in the viewer, repaints the scene); the button
 * only flips it and re-announces itself. Exported on its own because the drugs map page
 * (js/drugs-map-main.js) carries the same button but none of the 3D toggles.
 * @param {{get: () => string, toggle: () => string}} theme from createTheme
 */
export function wireThemeButton(theme) {
  const themeBtn = document.getElementById("toggle-theme");
  if (!themeBtn) return;
  const labelTheme = () => {
    const next = theme.get() === "dark" ? "light" : "dark";
    const label = t(next === "light" ? "panel.themeLight" : "panel.themeDark");
    themeBtn.setAttribute("title", label);
    themeBtn.setAttribute("aria-label", label);
  };
  labelTheme();
  themeBtn.addEventListener("click", () => { theme.toggle(); labelTheme(); });
}
