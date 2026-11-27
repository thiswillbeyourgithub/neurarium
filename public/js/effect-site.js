/**
 * The central / peripheral effect switch: one persisted choice ("all" | "central" |
 * "peripheral") that every effect listing honours (receptor + target Functional effects,
 * the drug panel's predicted effects, the Simulation's clinical-effects plot, the
 * Effects legend). Each effect row carries `site` ("central" | "peripheral" | "both",
 * from meta.receptor_effect_sites, see tools/data_generators/receptor_effects.py),
 * stamped by js/data/effects.js.
 *
 * A "both" effect (nausea, prolactin elevation) passes either filter, since the
 * question "does this happen in the brain?" is yes for it.
 *
 * Every switch built here is one view of the same pref: a click saves it and fires
 * EFFECT_SITE_EVENT on window, so a second open listing (the legend while a panel shows)
 * re-renders too. Pure filter + a tiny DOM builder; the filter is unit-tested by
 * tools/tests/effect_site.test.mjs.
 *
 * Built with the help of Claude Code.
 */
import { loadString, saveString } from "./prefs.js";

export const EFFECT_SITE_MODES = ["all", "central", "peripheral"];
export const EFFECT_SITE_EVENT = "neurarium:effect-site";
const SITE_KEY = "neurarium.effectSite";

/** The stored mode, "all" unless a valid other one was saved. */
export function loadEffectSite() {
  const raw = loadString(SITE_KEY);
  return EFFECT_SITE_MODES.includes(raw) ? raw : "all";
}

/**
 * Whether an effect of this site shows under this mode.
 * @param {string|undefined} site "central" | "peripheral" | "both" (missing = both)
 * @param {string} mode one of EFFECT_SITE_MODES
 * @returns {boolean} e.g. siteShown("peripheral", "central") === false,
 *   siteShown("both", "central") === true
 */
export function siteShown(site, mode) {
  return mode === "all" || !site || site === "both" || site === mode;
}

/** Keep the rows whose `site` shows under `mode` (default: the stored one). */
export function filterBySite(rows, mode = loadEffectSite()) {
  return (rows || []).filter((r) => siteShown(r.site, mode));
}

/**
 * A segmented switch (the shared .seg-switch look) over the stored mode.
 * @param {(mode: string) => void} onChange re-render the caller's listing
 * @returns {{el: HTMLElement, dispose: () => void}} `dispose` drops the window listener
 *   (call it when the listing is torn down; a detached switch also drops it lazily).
 */
export function buildEffectSiteSwitch(onChange) {
  const { t } = window.__I18N__;
  const box = document.createElement("div");
  box.className = "seg-switch effect-site-switch";
  box.setAttribute("role", "group");
  box.setAttribute("aria-label", t("effects.siteLabel"));
  const paint = (mode) => {
    for (const b of box.children) b.classList.toggle("active", b.dataset.mode === mode);
  };
  for (const mode of EFFECT_SITE_MODES) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "seg-btn";
    b.dataset.mode = mode;
    b.textContent = t(`effects.site.${mode}`);
    b.addEventListener("click", () => {
      saveString(SITE_KEY, mode);
      window.dispatchEvent(new CustomEvent(EFFECT_SITE_EVENT, { detail: mode }));
    });
    box.appendChild(b);
  }
  const onEvent = (ev) => {
    if (!box.isConnected && box.dataset.mounted) return dispose();
    paint(ev.detail);
    onChange(ev.detail);
  };
  const dispose = () => window.removeEventListener(EFFECT_SITE_EVENT, onEvent);
  window.addEventListener(EFFECT_SITE_EVENT, onEvent);
  // Mark once attached, so a switch built but not yet appended still hears its own click.
  queueMicrotask(() => { if (box.isConnected) box.dataset.mounted = "1"; });
  paint(loadEffectSite());
  return { el: box, dispose };
}
