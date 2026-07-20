// Single source of truth for the decorative-animation settings, read by every
// animated module so they all agree on one state. Three independent knobs:
//
//   - enabled: the user's "Animations" toggle (a Controls checkbox). When off, the
//     eye-candy motion stops (the assemble intro is skipped, the receptor/drug gem
//     dots stop twinkling and hold a static frame, the drug surface wash and the
//     circuit traveling pulse don't run) while the *content* still shows: focusing
//     a receptor/drug/circuit still lights its regions/arrows, just without motion.
//     Default ON for a fine pointer (desktop), OFF for a coarse pointer (phone) or
//     when the OS asks for reduced motion. The choice is persisted to localStorage,
//     so an explicit pick always wins over the heuristic default.
//
//   - quality: 0..1, the adaptive-rendering level (see createAdaptiveQuality in
//     js/main.js). The render loop drives it DOWN when it measures dropped frames
//     and back UP once they recover, so a weak GPU degrades gracefully instead of
//     stuttering. 1 = full detail. The renderer scales its devicePixelRatio by it
//     (the dominant cost lever) and the gem/bead builders scale their counts by it.
//     NOT persisted: it is a live measurement of this session's hardware, re-learned
//     each load (a resize / GPU-state change should be free to re-raise it).
//
//   - speed: the user's animation-speed multiplier (a Settings slider that surfaces
//     only while an animation is showing). 1 = the reference (baked) pace; the slider's
//     midpoint maps to 1 and its ends to [0.25x, 4x]. Every animated module multiplies
//     its per-frame time delta by this, so a live change re-paces without a phase jump.
//     Persisted to localStorage like `enabled` (an explicit preference, not a measurement).
//
// No dependency: a tiny observable holding two numbers. Modules import the shared
// `animSettings` singleton; nothing here touches three.js or the DOM beyond
// matchMedia + localStorage for the default/persistence.

const STORE_KEY = "neurarium.animations";
const SPEED_KEY = "neurarium.animspeed";

/** Speed multiplier bounds. 1 = the reference (baked) pace; the Settings slider maps its
 *  midpoint to 1 and its ends to these, so "50%" reads as the normal speed. */
const SPEED_MIN = 0.25;
const SPEED_MAX = 4;

function loadSpeed() {
  try {
    const v = parseFloat(localStorage.getItem(SPEED_KEY));
    if (Number.isFinite(v)) return Math.max(SPEED_MIN, Math.min(SPEED_MAX, v));
  } catch (_) {
    /* localStorage unavailable: fall back to the reference speed */
  }
  return 1;
}

/** The heuristic default when the user has made no explicit choice: on for a fine
 *  pointer (desktop/laptop), off for a coarse pointer (phone/tablet) or when the OS
 *  requests reduced motion. Recomputed live so the shipped checkbox reflects it. */
function detectDefault() {
  const mm = typeof window !== "undefined" && window.matchMedia;
  if (!mm) return true;
  const coarse = mm("(pointer: coarse)").matches;
  const reduced = mm("(prefers-reduced-motion: reduce)").matches;
  return !(coarse || reduced);
}

function loadEnabled() {
  try {
    const v = localStorage.getItem(STORE_KEY);
    if (v === "on") return true;
    if (v === "off") return false;
  } catch (_) {
    /* localStorage unavailable (private mode / disabled): fall back to the default */
  }
  return detectDefault();
}

let enabled = loadEnabled();
let quality = 1;
let speed = loadSpeed();
const subs = new Set();

function notify() {
  for (const fn of subs) fn();
}

export const animSettings = {
  /** Whether decorative animations run at all (the user's toggle). */
  get enabled() {
    return enabled;
  },
  /** Flip the toggle. Persists the choice and notifies subscribers on a change. */
  setEnabled(v) {
    v = !!v;
    if (v === enabled) return;
    enabled = v;
    try {
      localStorage.setItem(STORE_KEY, v ? "on" : "off");
    } catch (_) {
      /* ignore: persistence is best-effort */
    }
    notify();
  },
  /** The heuristic default (no stored override), for the checkbox's initial state. */
  get defaultEnabled() {
    return detectDefault();
  },

  /** The adaptive quality level, 0..1 (1 = full detail). */
  get quality() {
    return quality;
  },
  /** Set the quality level (clamped 0..1). Silent: the adaptive controller owns the
   *  side effects (devicePixelRatio + repaint), so a change here notifies no one. */
  setQuality(q) {
    quality = Math.max(0, Math.min(1, q));
  },

  /** The user's animation-speed multiplier (1 = the reference pace). Read live each
   *  frame by every animated module, so a change takes effect immediately. */
  get speed() {
    return speed;
  },
  /** Set the speed multiplier (clamped to [SPEED_MIN, SPEED_MAX]) and persist it, like
   *  `enabled`. Silent: the modules read `speed` live, so no subscriber needs waking. */
  setSpeed(v) {
    speed = Math.max(SPEED_MIN, Math.min(SPEED_MAX, Number(v) || 1));
    try {
      localStorage.setItem(SPEED_KEY, String(speed));
    } catch (_) {
      /* ignore: persistence is best-effort */
    }
  },
  /** The speed slider's bounds, so the UI's log mapping stays in sync with this module. */
  get speedRange() {
    return { min: SPEED_MIN, max: SPEED_MAX };
  },

  /** Subscribe to `enabled` changes; returns an unsubscribe fn. */
  subscribe(fn) {
    subs.add(fn);
    return () => subs.delete(fn);
  },
};
