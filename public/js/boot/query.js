// The page's `?query` string, parsed once at load (the app only ever rewrites the
// `#fragment`, see js/url-state.js, so the query cannot change under a session),
// plus the named predicates the boot reads off it. The classic js/i18n.js reads
// `?lang` on its own, since it runs before any module.

/** The parsed `location.search`. Read-only by convention. */
export const QUERY = new URLSearchParams(window.location.search);

/**
 * `?tour=1` forces the tour on every load, bypassing the once-per-visitor "seen"
 * gate and the eligibility checks (handy for testing / a shared link that always
 * runs it). It still waits for the intro and won't stack on an open popup.
 */
export const TOUR_FORCED = QUERY.get("tour") === "1";

/**
 * The query keys that describe a framed view (read by js/scene/camera.js
 * applyViewParams, documented in docs/RUNNING.md "?params"). Only these freeze
 * auto-rotate: a startup flag such as `?lang=fr` or `?tour=1` is not a view.
 */
export const VIEW_KEYS = Object.freeze(["view", "only", "solo", "ghost", "explode",
  "transparency", "names", "autorotate", "ui"]);

/**
 * Whether a query names a framed view (any of VIEW_KEYS), so it should hold still.
 * @param {URLSearchParams} params
 * @returns {boolean}
 */
export function isFramedView(params) {
  return VIEW_KEYS.some((k) => params.has(k));
}

/** `?explode=`: a deep link / screenshot fixes its own layout and framing. */
export const HAS_EXPLODE = QUERY.has("explode");

/**
 * An automated view (headless `?ui=0`, or an `?explode=` deep link / screenshot):
 * not a visit, so no loading-overlay wait, no tour, no release notes.
 */
export const AUTOMATED_VIEW = QUERY.get("ui") === "0" || HAS_EXPLODE;
