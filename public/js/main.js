// Entry point: builds the three.js scene from the dataset and wires the UI.
//
// Responsibilities kept here (vs the focused modules it imports):
//  - scene / camera / renderer / lights / OrbitControls setup
//  - load the data, build region meshes (js/shapes.js) and projection arrows
//    (js/arrows.js)
//  - the "explode" layout math (moving regions radially outward) and the
//    transparency control, plus auto-rotate
//  - the render loop
//
// OrbitControls already gives us the requested touch gestures for free:
// one finger = rotate, two fingers = pinch-zoom + pan.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { loadBrainData } from "./data.js";
import { buildStructureMesh } from "./shapes.js";
import { createSdfPool } from "./sdf-pool.js";
import { createLoadingScreen } from "./loading.js";
import { buildArrows } from "./arrows.js";
import { createLabels } from "./labels.js";
import { createCircuitAnimation } from "./circuit-anim.js";
import { createReceptorMarkers } from "./receptor-markers.js";
import { createDrugAnimation } from "./drug-anim.js";
import { animSettings } from "./anim-settings.js";
import { fetchWikiLead } from "./wiki.js";

// UI string lookup (js/i18n.js, a classic script that ran before this module).
// `t(key, vars)` returns the current-language UI string; data strings are
// already resolved to the chosen language by js/data.js.
const { t } = window.__I18N__;

// Explode slider is 0..1; this is how much extra radial distance the most
// outward regions travel at slider = 1 (as a multiple of their base distance
// from the brain center). Large enough that full separation spreads the regions
// well apart (the deep nuclei get plenty of room to be inspected); the camera
// maxDistance (see initThree) is comfortably beyond the farthest region so the
// user can zoom out to see the whole spread.
const EXPLODE_STRENGTH = 2.5;

// Intro animation: on a plain page load the brain starts fully blown out and
// settles together into the assembled whole over this many milliseconds, the
// camera pulling in from the spread (like dragging the Separate slider 1 -> 0)
// while it sweeps INTRO_ROTATION_TURNS of a turn and lands on the resting view.
// Tuned to feel swift but legible; eased so it departs and arrives smoothly.
const INTRO_DURATION_MS = 2200;
// How much of a full turn the camera sweeps during the intro before settling on
// the resting orientation (0.75 = three-quarters of a revolution).
const INTRO_ROTATION_TURNS = 0.75;
// When the dev / WIP banner is shown (DEV=1 container), the brain is presented a
// touch lower and further back so it sits clear below the banner: the resting
// camera is pulled out by this factor and the look-point lifted by this many
// world units (so the brain renders lower in the frame).
const DEV_BANNER_UNZOOM = 1.15;
const DEV_BANNER_DROP = 1.6;

// Drug-effect glyphs: a coloured symbol that stands in for the plain colour bar in
// a binding row, so the action's direction reads at a glance: + boost (increase),
// − block (decrease), ≈ modulate (roughly), each drawn in the effect's own colour
// (emerald / rose / violet).
const EFFECT_GLYPHS = { boost: "+", block: "−", modulate: "≈" };

// The glyph shown inside a NOSOURCE pill (no source document for the claim yet): a
// cross, so an unbacked node reads as a red ✕ at a glance rather than a long word.
// Shared by the info-panel pills (makeProvenancePill) and the About grade key, so
// the two never drift.
const NOSOURCE_GLYPH = "✕";

// Fold a string for accent- + case-insensitive matching: lowercase, then strip
// combining diacritical marks (NFD decomposes e.g. "é" -> "e" + U+0301, "ç" ->
// "c" + U+0327, which we then drop). So the search/filter find "sérotonine" when
// the user types "seroto", and ignore case (see foldText below). Used by the
// toolbar search + the drug filter so both behave the same.
//
// Greek letter -> its spelled-out Latin name, so a folded string matches whether
// the data uses the glyph (the receptor names: "\u03b12A", "\u03bc (MOR)", "\u03c31") or the user
// types the name they CAN reach on a keyboard ("alpha2a", "mu", "sigma1"). Folding
// both sides through this means "beta" finds "\u03b21" and "alpha" finds "\u03b12A".
const GREEK_NAMES = {
  "\u03b1": "alpha", "\u03b2": "beta", "\u03b3": "gamma", "\u03b4": "delta",
  "\u03b5": "epsilon", "\u03b6": "zeta", "\u03b7": "eta", "\u03b8": "theta",
  "\u03b9": "iota", "\u03ba": "kappa", "\u03bb": "lambda", "\u03bc": "mu",
  "\u03bd": "nu", "\u03be": "xi", "\u03bf": "omicron", "\u03c0": "pi",
  "\u03c1": "rho", "\u03c3": "sigma", "\u03c2": "sigma", "\u03c4": "tau",
  "\u03c5": "upsilon", "\u03c6": "phi", "\u03c7": "chi", "\u03c8": "psi",
  "\u03c9": "omega",
};

function foldText(s) {
  return String(s)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    // Spell out Greek letters (after lowercasing, so uppercase \u0391 already became \u03b1),
    // then drop hyphens / Unicode dashes so "5ht" finds "5-HT".
    .replace(/[\u0370-\u03ff]/g, (ch) => GREEK_NAMES[ch] || ch)
    .replace(/[-\u2010-\u2015]/g, "");
}

// Structured search filters: a leading `field:value` (value optionally quoted)
// narrows results to a kind of item by one of its fields. The field name is matched
// accent/case-folded so the English + French names both work. Only drug fields for
// now (class / nomenclature); a drug panel's clickable Class / Nomenclature builds
// such a query. The map's values are the canonical field keys the items carry.
const SEARCH_FIELDS = {
  class: "class", classe: "class",
  nbn: "nbn", nomenclature: "nbn",
};

// Split a raw query into { field, value, rest }: a recognized `field:"value"`
// prefix (else field=null), plus any trailing free text. value + rest come back
// already folded; an unrecognized field is left as plain free text.
function parseSearchQuery(raw) {
  const m = String(raw).match(/^\s*([\p{L}]+)\s*:\s*(?:"([^"]*)"|(\S*))\s*([\s\S]*)$/u);
  if (m) {
    const field = SEARCH_FIELDS[foldText(m[1])];
    if (field) {
      const value = foldText(m[2] !== undefined ? m[2] : (m[3] || ""));
      return { field, value, rest: foldText((m[4] || "").trim()) };
    }
  }
  return { field: null, value: "", rest: foldText(String(raw).trim()) };
}

/** Build scene, camera, renderer and controls. @returns {object} the bundle. */
function initThree() {
  const canvas = document.getElementById("scene");
  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#0e1116");

  const camera = new THREE.PerspectiveCamera(
    50,
    window.innerWidth / window.innerHeight,
    0.1,
    1000,
  );
  // Pulled back from the old (9, 4.5, 13): the default view was a touch too
  // zoomed in, so the resting framing leaves a little more room around the brain.
  camera.position.set(11, 5.5, 16);

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  // Cap the device pixel ratio at 2 (a retina phone can report 3+, which quadruples
  // the pixel work for no visible gain). This is the *base* ratio; the adaptive
  // quality controller (see createAdaptiveQuality) scales it down transiently when
  // it detects dropped frames, then this same base is the ceiling it recovers to.
  const baseDpr = Math.min(window.devicePixelRatio, 2);
  renderer.setPixelRatio(baseDpr);
  renderer.setSize(window.innerWidth, window.innerHeight);

  // Soft, even lighting so colors read true and the blobs keep visible relief.
  scene.add(new THREE.HemisphereLight(0xffffff, 0x33373d, 0.9));
  const key = new THREE.DirectionalLight(0xffffff, 0.8);
  key.position.set(6, 10, 8);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xbfd4ff, 0.35);
  fill.position.set(-8, -4, -6);
  scene.add(fill);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.rotateSpeed = 0.9;
  controls.minDistance = 4;
  // Comfortably beyond the fully-separated spread so the intro's zoom-out (the
  // resting distance times the explode spread factor) isn't clamped mid-greeting.
  controls.maxDistance = 75;
  // Pan in screen space so a two-finger drag slides the brain across the view
  // (rather than along world axes), which feels natural on touch.
  controls.enablePan = true;
  controls.screenSpacePanning = true;
  // Touch mapping: one finger rotates, two fingers pan AND pinch-zoom together
  // (DOLLY_PAN). Pinned here so it survives future control tweaks.
  controls.touches = {
    ONE: THREE.TOUCH.ROTATE,
    TWO: THREE.TOUCH.DOLLY_PAN,
  };

  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  return { scene, camera, renderer, controls, baseDpr };
}

/**
 * Position every region for a given explode amount, pushing each radially
 * outward from the brain center along its stored direction.
 * @param {THREE.Mesh[]} meshes
 * @param {number} amount  Slider value in [0, 1].
 * @param {import("./arrows.js").ProjectionArrow[]} arrows
 * @param {boolean} [fast]  Re-fit arrows cheaply (skip the surface-trim raycasts,
 *   ~90% of the cost) for a smooth continuous spread; a deferred precise re-trim
 *   (createArrowRetrim) cleans up once the spread settles.
 */
function applyExplode(meshes, amount, arrows, fast = false) {
  for (const mesh of meshes) {
    const { base, dir } = mesh.userData;
    const distance = base.length() * amount * EXPLODE_STRENGTH;
    mesh.position.copy(base).addScaledVector(dir, distance);
  }
  // Arrows follow the moved centers.
  for (const arrow of arrows) arrow.update(fast);
}

/**
 * Deferred precise arrow re-trim for the explode path. During a continuous spread
 * the arrows are re-fit cheaply (applyExplode `fast`), which skips the surface-trim
 * raycasts and so leaves each end slightly facing the pre-spread direction. Once
 * the spread has been still for SETTLE_MS this re-trims every arrow precisely, a
 * CHUNK at a time per frame so the catch-up never lands as one hitch.
 *
 * It plugs into the render loop like the other per-frame controllers: `tick()`
 * runs every frame (the loop callback is continuous; only the render is on-demand)
 * and returns whether it changed anything, so the loop repaints the corrected
 * arrows. `markDirty()` is called after each fast spread update to (re)arm it.
 * @param {import("./arrows.js").ProjectionArrow[]} arrows
 */
function createArrowRetrim(arrows) {
  const SETTLE_MS = 120; // re-trim this long after the last spread change
  const CHUNK = 24;      // arrows re-trimmed per frame while catching up
  let lastChange = -Infinity;
  let cursor = arrows.length; // < length while a precise pass is in flight

  return {
    /** Note a fast (imprecise) spread update; (re)start the settle timer and
     *  abandon any in-flight catch-up (it would fight the active spread). */
    markDirty() {
      lastChange = performance.now();
      cursor = arrows.length;
    },
    /** Per-frame: drive the deferred re-trim. Returns true while it has work. */
    tick() {
      if (cursor < arrows.length) {
        const end = Math.min(cursor + CHUNK, arrows.length);
        for (; cursor < end; cursor++) arrows[cursor].update(); // precise + re-caches
        return true; // arrows changed: keep rendering
      }
      if (lastChange !== -Infinity && performance.now() - lastChange >= SETTLE_MS) {
        lastChange = -Infinity;
        cursor = 0; // begin a precise pass over the next frames
        return true;
      }
      return false;
    },
  };
}

/**
 * Keep projection arrows a constant *apparent* width as the camera zooms. A
 * zoomed-in arrow would otherwise balloon and clutter the view (and a zoomed-out
 * one thin away to nothing); scaling the shaft radius + cone cross-section by the
 * camera<->target distance holds the on-screen width roughly put.
 *
 * The reference distance (width scale 1) is captured on the first tick, so the
 * resting framing keeps the authored arrow width. The explode auto-zoom
 * (zoomForExplode pulls the camera back as the brain spreads) is divided out via
 * focus.explodeZoom(), so a spread does NOT rescale arrows: it would fight the
 * per-frame explode rebuild for no visual gain (the brain holds a constant
 * apparent size while spreading anyway). Only a genuine user zoom changes width.
 *
 * Plugs into the render loop like the other controllers: tick() runs each frame
 * and returns whether it changed any arrow, so the on-demand loop repaints. A
 * width-step threshold avoids rebuilding on sub-pixel damping jitter.
 * @param {{arrows:import("./arrows.js").ProjectionArrow[], camera:THREE.PerspectiveCamera,
 *   controls:import("three/addons/controls/OrbitControls.js").OrbitControls,
 *   focus:ReturnType<typeof createCameraFocus>}} deps
 */
function createArrowWidth({ arrows, camera, controls, focus }) {
  const MIN = 0.4;   // never thinner than 40% (stays visible zoomed all the way in)
  const MAX = 2.4;   // never fatter than 240% (zoomed all the way out)
  const STEP = 0.02; // re-fit only when the scale moves at least this much
  let refDist = null; // resting (explode-zoom-divided-out) distance = scale 1
  let applied = 1;
  const tmp = new THREE.Vector3();
  // The camera<->target distance with the explode auto-pull removed, i.e. the
  // distance the user's own zoom implies.
  const userDist = () =>
    tmp.copy(camera.position).sub(controls.target).length() / focus.explodeZoom();
  return {
    /** Per-frame: rescale every arrow to hold a constant apparent width.
     *  Returns true only when a width step was actually applied. */
    tick() {
      const dist = userDist();
      if (refDist === null) { refDist = dist; return false; }
      const scale = Math.max(MIN, Math.min(MAX, dist / refDist));
      if (Math.abs(scale - applied) < STEP) return false;
      applied = scale;
      let changed = false;
      for (const a of arrows) if (a.setWidthScale(scale)) changed = true;
      return changed;
    },
  };
}

// "See inside" cull: how far past the orbit-centre plane (toward the camera) a
// structure's centre must sit before it is hidden. A positive bias keeps the
// central core (the deep nuclei) visible while the near outer hemisphere drops
// away, so you can look at the inside without the front cortex in the way.
const NEAR_CULL_BIAS = 0.9;

/**
 * Toggleable "see inside" mode: hide the structures on the camera-facing side of
 * the brain so the deep nuclei aren't blocked by the near cortex. The hidden set
 * is recomputed every frame from the live camera/target, so it follows as you
 * orbit. Composes with `?only=` (a mesh already hidden stays hidden) and with
 * isolate mode (which dims via opacity, not visibility). Off by default.
 *
 * @param {{meshes:THREE.Mesh[], camera:THREE.Camera,
 *          controls:import("three/addons/controls/OrbitControls.js").OrbitControls}} deps
 */
function createNearCull({ meshes, camera, controls }) {
  let enabled = false;
  const center = new THREE.Vector3();
  const viewOut = new THREE.Vector3();
  const toMesh = new THREE.Vector3();
  return {
    /** Enable/disable. On enable, snapshot current visibility so disable restores
     *  exactly that (e.g. meshes hidden by ?only= stay hidden). */
    setEnabled(on) {
      if (on === enabled) return;
      enabled = on;
      if (on) {
        for (const m of meshes) m.userData.cullRestore = m.visible;
      } else {
        for (const m of meshes) {
          if (m.userData.cullRestore !== undefined) {
            m.visible = m.userData.cullRestore;
          }
        }
      }
    },
    /** Per-frame: hide every otherwise-visible structure whose centre is more
     *  than NEAR_CULL_BIAS past the orbit-centre plane toward the camera. */
    tick() {
      if (!enabled) return;
      viewOut.copy(camera.position).sub(controls.target);
      if (viewOut.lengthSq() < 1e-9) return;
      viewOut.normalize();
      center.copy(controls.target);
      for (const m of meshes) {
        if (!m.userData.cullRestore) {
          m.visible = false;
          continue;
        }
        toMesh.copy(m.position).sub(center);
        m.visible = toMesh.dot(viewOut) <= NEAR_CULL_BIAS;
      }
    },
  };
}

/**
 * Adaptive-quality controller: watches the frame time while the scene is animating
 * and, if it stays slow, steps the shared `animSettings.quality` DOWN (and steps it
 * back UP once frames recover). Quality's dominant effect is the renderer's
 * devicePixelRatio (fewer pixels shaded per frame = the biggest cheap win against
 * the additive-glow overdraw of the gem/wash animations); the gem-dot + circuit-bead
 * builders also read it to scatter fewer primitives on the next focus.
 *
 * It only samples frames the loop actually *rendered* while animating (an idle frame
 * costs nothing and would skew the timing), and uses hysteresis (needs several slow
 * frames in a row to drop, many good ones to recover) plus a comfortable middle band
 * so it settles instead of oscillating. `tick(rendered)` is called once per frame
 * from the render loop with whether an animated render happened; it returns true when
 * it changed the level (so the loop repaints at the new pixel ratio).
 * @param {{renderer:THREE.WebGLRenderer, baseDpr:number}} deps
 */
function createAdaptiveQuality({ renderer, baseDpr }) {
  const MIN_Q = 0.6;       // never below 60% detail / pixel ratio
  const STEP = 0.1;
  const SLOW_MS = 30;      // a frame slower than this (~<33fps) counts as "slow"
  const FAST_MS = 20;      // a frame faster than this (~>50fps) counts as "fast"
  const SLOW_FRAMES = 20;  // this many slow frames in a row -> step down
  const FAST_FRAMES = 90;  // this many fast frames in a row -> step back up
  let lastT = null;
  let slow = 0;
  let fast = 0;

  // three's setPixelRatio re-applies the stored CSS size internally, and a later
  // renderer.setSize (the resize handler) keeps this ratio, so setting it here is
  // enough; no resize re-apply is needed.
  const applyDpr = () => renderer.setPixelRatio(baseDpr * animSettings.quality);

  return {
    tick(rendered) {
      // Only measure while continuously animating: an idle frame is an early-out
      // (no render), so its huge delta must not be read as a slow render.
      if (!rendered) {
        lastT = null;
        return false;
      }
      const now = performance.now();
      if (lastT === null) {
        lastT = now;
        return false;
      }
      const dt = now - lastT;
      lastT = now;
      if (dt > SLOW_MS) {
        slow += 1;
        fast = 0;
      } else if (dt < FAST_MS) {
        fast += 1;
        slow = 0;
      } else {
        slow = 0; // comfortable band: reset both, hold the current level
        fast = 0;
      }
      if (slow >= SLOW_FRAMES && animSettings.quality > MIN_Q) {
        animSettings.setQuality(Math.max(MIN_Q, animSettings.quality - STEP));
        applyDpr();
        slow = 0;
        return true;
      }
      if (fast >= FAST_FRAMES && animSettings.quality < 1) {
        animSettings.setQuality(Math.min(1, animSettings.quality + STEP));
        applyDpr();
        fast = 0;
        return true;
      }
      return false;
    },
  };
}

/**
 * Auto-play intro: start the regions fully blown out and let them glide back
 * together into the assembled brain, exactly like dragging the Separate slider
 * from 1 to 0. The camera follows the spread (zoomForExplode, so the brain keeps
 * a steady apparent size) and at the same time sweeps INTRO_ROTATION_TURNS of a
 * revolution, both finishing together on the resting view. Advanced once per
 * frame by `tick()` from the render loop. `cancel()` stops it (and restores
 * auto-rotate) so a manual grab of the explode slider always wins. Uses
 * easeInOutCubic for a smooth departure + gentle settle.
 * @param {{meshes:THREE.Mesh[], arrows:object[], slider:HTMLInputElement,
 *   camera:THREE.PerspectiveCamera, controls:OrbitControls,
 *   focus:ReturnType<typeof createCameraFocus>}} deps
 */
function createIntroAnimation({ meshes, arrows, slider, camera, controls, focus }) {
  const FROM = 1; // fully blown out (slider max)
  const TO = 0; // assembled whole
  const SWEEP = INTRO_ROTATION_TURNS * Math.PI * 2; // radians to sweep in
  let startTime = null; // set on the first tick so load jank isn't counted
  let running = false;
  let restAzimuth = 0; // azimuth/polar of the resting pose to land on at t=1
  let restPolar = 0;
  let wasAutoRotate = false; // restored when the intro ends / is cancelled
  const tmpOffset = new THREE.Vector3();
  const sph = new THREE.Spherical();

  // easeInOutCubic: starts and ends at rest, fastest through the middle.
  const ease = (t) =>
    t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

  const applyAmount = (amount) => {
    // Set the slider directly (no input event) so this doesn't trip the
    // user-input cancel listener wired alongside it.
    slider.value = String(amount);
    applyExplode(meshes, amount, arrows);
  };

  // We drive the rotation ourselves during the intro, so OrbitControls' own
  // auto-rotate must be off until we hand back at the end (or on cancel).
  const finish = () => {
    running = false;
    controls.autoRotate = wasAutoRotate;
  };

  return {
    start() {
      running = true;
      startTime = null;
      wasAutoRotate = controls.autoRotate;
      controls.autoRotate = false;
      // Capture the resting camera azimuth/polar so the sweep lands exactly on
      // the default view; only azimuth + distance animate (polar held fixed).
      tmpOffset.copy(camera.position).sub(controls.target);
      sph.setFromVector3(tmpOffset);
      restAzimuth = sph.theta;
      restPolar = sph.phi;
      applyAmount(FROM);
    },
    cancel() {
      if (running) finish();
    },
    tick() {
      if (!running) return false;
      if (startTime === null) startTime = performance.now();
      const t = Math.min(1, (performance.now() - startTime) / INTRO_DURATION_MS);
      const e = ease(t);
      const amount = FROM + (TO - FROM) * e;
      applyAmount(amount);
      // Camera distance tracks the spread (telescoping back to the resting
      // distance at amount 0), exactly like the Separate slider does.
      focus.zoomForExplode(amount);
      // Sweep the azimuth in toward the resting angle; hold the polar + the
      // distance zoomForExplode just set.
      tmpOffset.copy(camera.position).sub(controls.target);
      sph.setFromVector3(tmpOffset);
      sph.theta = restAzimuth - (1 - e) * SWEEP;
      sph.phi = restPolar;
      sph.makeSafe();
      tmpOffset.setFromSpherical(sph);
      camera.position.copy(controls.target).add(tmpOffset);
      if (t >= 1) finish();
      return true; // animating (incl. the finishing frame), so keep rendering
    },
  };
}

/**
 * Auto-spread controller: smoothly drives the explode slider UP to a target
 * amount, the same thing the user would do by dragging the Separate slider, so a
 * deep (inside) structure isn't left hidden under the cortex when it is focused
 * from search / a detail panel. `apply(amount)` is the shared explode applier
 * (layout + camera re-aim + zoom), so a spread tracks the focused structure and
 * keeps the apparent size exactly like a manual drag. Advanced by `tick()` in the
 * render loop. Only ever raises the spread (never collapses it), and never lowers
 * below the current value, so it composes with whatever the user already set.
 * @param {{slider:HTMLInputElement, apply:(amount:number)=>void}} deps
 */
function createAutoSpread({ slider, apply }) {
  const DURATION_MS = 600;
  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  let running = false;
  let startTime = null;
  let from = 0;
  let to = 0;
  return {
    /** Animate the spread up to `target` (0..1). No-op if already at/above it. */
    spreadTo(target) {
      const current = parseFloat(slider.value);
      if (current >= target - 1e-3) return; // already spread enough
      from = current;
      to = target;
      startTime = null;
      running = true;
    },
    /** Stop the auto-spread (a manual slider grab wins). */
    cancel() {
      running = false;
    },
    tick() {
      if (!running) return false;
      if (startTime === null) startTime = performance.now();
      const t = Math.min(1, (performance.now() - startTime) / DURATION_MS);
      const amount = from + (to - from) * ease(t);
      slider.value = String(amount);
      apply(amount);
      if (t >= 1) running = false;
      return true;
    },
  };
}

/**
 * Selection + isolation controller. Owns the per-structure highlight halos, the
 * structure/arrow opacity, and the legend-greying hook, so all three stay in one
 * consistent state.
 *
 * Two overlapping ideas, both surfaced through the halos built below:
 *   - a lightweight *highlight* (`select`): the single structure picked in the
 *     3D view (click / double-click / search). Halo only, no dimming, so the
 *     region is shown in context.
 *   - an *isolate* set (`toggleIsolate`, fed by clicking legend rows): while it
 *     is non-empty the scene focuses on those structures. Every other structure
 *     drops to a faint opacity, arrows that don't touch an isolated structure
 *     fade with them, the isolated structures keep full (slider) opacity + halo,
 *     and the legend greys its non-isolated rows (via the `onIsolate` callback).
 *     The reset button (`clear`) empties it.
 *
 * Opacity is composed here rather than in a standalone helper because the
 * isolate dimming and the transparency slider must combine into one final
 * opacity per mesh: `setBaseOpacity` records the slider value and every reapply
 * derives each mesh/arrow opacity from that base plus the isolate state.
 *
 * Each structure gets one hidden "shell" child for its halo: its own geometry,
 * scaled up a touch and drawn back-faces-only with an additive, non-depth-
 * writing material in a lightened version of the structure's colour. Rendering
 * only the back side of the slightly larger shell shows just the sliver poking
 * out past the real mesh (a coloured rim/aura), and additive blending makes it
 * read as light rather than a solid outline. Parenting the shell to the mesh
 * lets it inherit every transform (explode, mirror, position) for free, so the
 * halo tracks the structure with zero per-frame work, and it reuses the mesh
 * geometry (no clone). This keeps the no-build, single-pass renderer intact (no
 * EffectComposer / OutlinePass post-processing).
 *
 * @param {{meshes:THREE.Mesh[], arrows:import("./arrows.js").ProjectionArrow[]}} deps
 * @returns {{
 *   setBaseOpacity: (o:number) => void,
 *   select: (mesh: THREE.Mesh|null) => void,
 *   toggleIsolate: (group: THREE.Mesh[]) => void,
 *   clear: () => void,
 *   getSelected: () => {meshes:Set<THREE.Mesh>, arrows:Set<object>}|null,
 *   onIsolate: (fn: (isolated: Set<THREE.Mesh>|null) => void) => void,
 * }}
 */
function createSelection({ meshes, arrows }) {
  // How far the halo shell extends past the real surface: small, so the rim is a
  // thin glow rather than a fat outline.
  const SCALE = 1.06;
  // Opacity that isolate mode drops everything *not* selected to (structures and
  // unrelated arrows alike): faint enough that the focus pops, but not fully
  // gone, so the rest of the brain still reads as context.
  const DIM = 0.12;
  const white = new THREE.Color(0xffffff);

  for (const mesh of meshes) {
    // Lighten the structure's own colour toward white so the rim reads as light
    // regardless of how dark/saturated the region is, while still tying back to it.
    const color = new THREE.Color(mesh.userData.structure.color).lerp(white, 0.35);
    const material = new THREE.MeshBasicMaterial({
      color,
      side: THREE.BackSide, // only the rim poking past the real mesh shows
      transparent: true,
      opacity: 0.6,
      blending: THREE.AdditiveBlending, // brightens the background -> glow, not paint
      depthWrite: false, // a glow must not occlude anything behind it
    });
    const shell = new THREE.Mesh(mesh.geometry, material);
    shell.scale.setScalar(SCALE);
    shell.visible = false;
    // Pure decoration: never let the halo intercept picking/hover raycasts.
    shell.raycast = () => {};
    mesh.add(shell);
    mesh.userData.halo = shell;
  }

  let highlighted = null; // single 3D-pick structure highlight (halo only)
  let highlightedArrow = null; // single picked arrow (halo only)
  const isolated = new Set(); // legend multi-select (drives the dimming)
  // Explicit arrow focus for circuits: when non-empty, *only* these arrows stay
  // opaque. When empty, isolate mode falls back to "arrows touching an isolated
  // structure" (so a plain structure isolate still lights up its connections).
  const isolatedArrows = new Set();
  let baseOpacity = 1; // current transparency-slider value
  // Focus-change subscribers, each called on every apply() with the live isolate
  // state. Multiple because both the legend (greying) and the circuit pulse
  // animation (stop when the focus is no longer its circuit) need to react.
  const onIsolateSubs = [];
  // Highlight-change subscribers, each called with the single haloed structure
  // mesh (or null) on every apply(). The label overlay uses this to pin the
  // selected structure's name (a structure pick sets `highlighted`; an arrow /
  // target / drug focus or a clear nulls it), so the pinned name follows exactly
  // the active single-structure selection. Idempotent downstream (setPinned
  // early-returns on no change), so re-firing every apply() is cheap.
  const onHighlightSubs = [];
  // Fired whenever the user actively picks content (a structure, an arrow, a
  // legend isolate, or a circuit), but not on a clear. Used to stop auto-rotate
  // once the user reaches in to inspect something. Set via onPick().
  let onPickContent = () => {};

  const touchesIsolated = (arrow) =>
    isolated.has(arrow.fromMesh) || isolated.has(arrow.toMesh);
  // Is an arrow part of the current focus? Circuits pin an explicit arrow set;
  // otherwise any arrow touching an isolated structure counts.
  const arrowInFocus = (arrow) =>
    isolatedArrows.size > 0 ? isolatedArrows.has(arrow) : touchesIsolated(arrow);

  // Recompute halos + opacity from the current highlight/isolate/base state. One
  // function so the triggers (3D pick, legend, circuits) can never drift apart.
  function apply() {
    const active = isolated.size > 0;
    for (const mesh of meshes) {
      const halo = mesh.userData.halo;
      if (halo) {
        halo.visible = mesh.visible && (mesh === highlighted || isolated.has(mesh));
      }
      // Isolated (or no isolation) -> the slider opacity; everything else faint.
      const op = !active || isolated.has(mesh) ? baseOpacity : Math.min(baseOpacity, DIM);
      mesh.material.opacity = op;
      mesh.material.depthWrite = op >= 0.99;
    }
    // Arrows: keep those in the focus opaque, fade the rest into the background
    // with the dimmed structures; the picked arrow also lights its halo.
    for (const arrow of arrows) {
      arrow.setOpacity(!active || arrowInFocus(arrow) ? 1 : DIM);
      arrow.setHalo(arrow === highlightedArrow);
    }
    // Pass the pinned-arrow set too (empty unless a circuit/kind is focused) so
    // the legend can tell *which* projection-kind/circuit row is the active one.
    for (const fn of onIsolateSubs) fn(active ? isolated : null, isolatedArrows);
    for (const fn of onHighlightSubs) fn(highlighted);
  }

  return {
    /** Record the transparency slider value (composes with isolate dimming). */
    setBaseOpacity(o) {
      baseOpacity = o;
      apply();
    },
    /** Is this mesh currently in the isolate/focus set? */
    isIsolated(mesh) {
      return isolated.has(mesh);
    },
    /** Lightweight single structure highlight from a 3D pick (null clears it). */
    select(mesh) {
      const next = mesh && mesh.userData.halo ? mesh : null;
      if (next === highlighted && highlightedArrow === null) return;
      highlighted = next;
      highlightedArrow = null; // a structure and an arrow halo are mutually exclusive
      apply();
      if (next) onPickContent();
    },
    /** Halo a single picked arrow (click/search); null clears it. */
    selectArrow(arrow) {
      if (arrow === highlightedArrow && highlighted === null) return;
      highlightedArrow = arrow || null;
      highlighted = null;
      apply();
      if (highlightedArrow) onPickContent();
    },
    /**
     * Toggle a group of meshes (a legend row's L/R pair, or a whole category) in
     * the isolate set: remove them if all are already isolated, else add them
     * all, so the click reads as a single on/off. Drops any circuit arrow-pin so
     * the focus reverts to "connections of the isolated structures".
     */
    toggleIsolate(group) {
      const allIn = group.length > 0 && group.every((m) => isolated.has(m));
      for (const m of group) {
        if (allIn) isolated.delete(m);
        else isolated.add(m);
      }
      isolatedArrows.clear();
      apply();
      onPickContent();
    },
    /**
     * Replace the whole focus with an explicit circuit: just `meshes` opaque +
     * just `circuitArrows` opaque, everything else faint. Empty args clear it.
     */
    setCircuit(circuitMeshes, circuitArrows) {
      isolated.clear();
      isolatedArrows.clear();
      for (const m of circuitMeshes) isolated.add(m);
      for (const a of circuitArrows) isolatedArrows.add(a);
      highlighted = null;
      highlightedArrow = null;
      apply();
      if (circuitMeshes.length) onPickContent();
    },
    /** Clear every highlight + isolate, restoring default opacity everywhere. */
    clear() {
      highlighted = null;
      highlightedArrow = null;
      isolated.clear();
      isolatedArrows.clear();
      apply();
    },
    /**
     * The currently focused meshes + arrows (whatever stays opaque): the isolate
     * set (legend / circuit / projection-group) plus any single halo'd structure,
     * and the in-focus arrows plus any single halo'd arrow. Returns null when
     * nothing is selected. Used to scope "show all names" to just the selection.
     */
    getSelected() {
      const sm = new Set(isolated);
      if (highlighted) sm.add(highlighted);
      const sa = new Set();
      if (isolated.size > 0) {
        for (const a of arrows) if (arrowInFocus(a)) sa.add(a);
      }
      if (highlightedArrow) sa.add(highlightedArrow);
      if (sm.size === 0 && sa.size === 0) return null;
      return { meshes: sm, arrows: sa };
    },
    /**
     * Re-emit the current state to every subscriber (halos/opacity/legend greying)
     * without changing it. Used after the legend is rebuilt (colour-mode toggle)
     * so the fresh rows reflect the live isolate set immediately.
     */
    refresh() {
      apply();
    },
    /**
     * Register a focus-change callback, invoked with the live isolate set (or
     * null when nothing is isolated) and the pinned-arrow set on every change.
     * Multiple may be registered (legend greying + circuit-pulse stop). Applied
     * once now so the new subscriber reflects the current state immediately.
     */
    onIsolate(fn) {
      onIsolateSubs.push(fn);
      apply();
    },
    /**
     * Register a callback fired with the single haloed structure mesh (or null)
     * whenever it changes. Used to pin the selected structure's floating name.
     * Applied once now so the subscriber reflects the current highlight.
     */
    onHighlight(fn) {
      onHighlightSubs.push(fn);
      fn(highlighted);
    },
    /**
     * Register a callback fired whenever the user actively picks content (a
     * structure, an arrow, a legend isolate, or a circuit) but not on a clear.
     * Used to stop auto-rotate once the user reaches in to inspect something.
     */
    onPick(fn) {
      onPickContent = fn;
    },
  };
}

/**
 * Append one swatch+label row to a container. `line` renders a thin bar.
 * @returns {HTMLElement} the created row, so callers can wire it up.
 */
function addLegendItem(container, color, label, line = false) {
  const row = document.createElement("div");
  row.className = "legend-item";
  const swatch = document.createElement("span");
  swatch.className = line ? "swatch line" : "swatch";
  swatch.style.background = color;
  row.append(swatch, document.createTextNode(label));
  container.appendChild(row);
  return row;
}

/**
 * Build the legend from the live dataset so it can never drift from what is
 * actually drawn. Left/right pairs share a color and are collapsed to a single
 * entry (hemisphere prefix stripped); clicking a structure row isolates that
 * structure (both hemispheres) via the selection controller, and the controller
 * greys back the non-isolated rows so the legend doubles as the focus filter.
 * @param {import("./data.js").BrainData} data
 * @param {Map<string, THREE.Mesh>} meshById  structure id -> its mesh.
 * @param {import("./arrows.js").ProjectionArrow[]} arrows
 * @param {ReturnType<typeof createSelection>} selection
 */
/**
 * Shared control of which projection arrows are visible, so the global "Hide
 * projections" button and the legend's off-by-default "Hypothetical pathways"
 * toggle compose into one final per-arrow visibility instead of fighting over
 * setVisible(). An arrow shows when projections aren't globally hidden AND it is
 * either established or (when tentative) its section has been toggled on, so
 * speculative pathways start hidden.
 * @param {import("./arrows.js").ProjectionArrow[]} arrows
 * @param {{refresh: () => void}} labels  Refreshed after a change so the
 *   connection labels follow their arrows' visibility.
 */
function createProjectionVisibility(arrows, labels) {
  let allHidden = false;
  let tentativeShown = false;
  const apply = () => {
    for (const a of arrows) {
      a.setVisible(!allHidden && (!a.tentative || tentativeShown));
    }
    labels.refresh();
  };
  return {
    apply,
    get allHidden() { return allHidden; },
    setAllHidden(v) { allHidden = v; apply(); },
    get tentativeShown() { return tentativeShown; },
    setTentativeShown(v) { tentativeShown = v; apply(); },
  };
}

/**
 * Group the (established) projection arrows into the rows the legend's Projections
 * section shows, one entry per row. Two groupings, picked by the colour-mode
 * toggle, so the legend always matches the arrow colours on screen:
 *   - "transmitter" (default): one row per neurotransmitter molecule, coloured by
 *     its arrow colour and labelled "Molecule (kind)";
 *   - "sign": one row per excitatory/inhibitory/modulatory class, coloured by the
 *     sign swatch and labelled by the (localized) sign heading.
 * Each entry is `{ key, label, color, arrows }`; `key` just identifies the row.
 * @param {import("./arrows.js").ProjectionArrow[]} established  Non-tentative arrows.
 * @param {import("./data.js").BrainData["meta"]} meta
 * @param {boolean} signMode
 */
function projectionGroups(established, meta, signMode) {
  if (signMode) {
    // Sign order follows meta.signLabels (excitatory, inhibitory, modulatory).
    return Object.keys(meta.signLabels || {})
      .map((sign) => ({
        key: `sign:${sign}`,
        // The projection_groups.jsonl record id for this row's sourced data
        // panel (mode:key), so a row click can open its detail tab.
        dataKey: `sign:${sign}`,
        label: meta.signLabels[sign] || sign,
        color: meta.signColors[sign] || "#fff",
        arrows: established.filter((a) => a.projection.sign === sign),
      }))
      .filter((g) => g.arrows.length > 0);
  }
  const molecules = [...new Set(established.map((a) => a.projection.neurotransmitter).filter(Boolean))];
  return molecules.map((nt) => {
    const group = established.filter((a) => a.projection.neurotransmitter === nt);
    const kind = group[0] && group[0].projection.kind;
    const kindLabel = kind ? (meta.kindLabels[kind] || kind) : "";
    return {
      key: `nt:${nt}`,
      // The data panel is per-*kind* (the record key is `kind:<kind>`), so a row
      // resolves its sourced record by kind even though the row itself is split
      // per-neurotransmitter (kind <-> transmitter is 1:1 today; were a kind to
      // carry two transmitters, both rows would open the same kind panel).
      dataKey: kind ? `kind:${kind}` : null,
      label: kindLabel ? `${nt} (${kindLabel})` : nt,
      color: (group[0] && group[0].projection.color) || "#fff",
      arrows: group,
    };
  });
}

/**
 * Build the two interactive browser sections from the live dataset: the region
 * rows (into #structures-body) and the projection / circuit / hypothetical rows
 * (into #projections-body). The static colour key is a separate section, built
 * once by buildLegendKey (it doesn't depend on the colour mode). Returns the
 * focus-change `reflect` callback (greys non-isolated rows across *both* sections,
 * so the focus-state logic isn't duplicated); the caller registers it once and
 * re-invokes buildLegend (reassigning reflect) when the colour mode toggles, so
 * the Projections rows follow the arrow colours without stacking onIsolate
 * listeners.
 * @param {boolean} signColorMode  Colour arrows/legend by excit/inhib sign.
 * @returns {(isolated: Set<THREE.Mesh>|null, focusedArrows: Set<object>) => void}
 */
function buildLegend(data, meshById, arrows, selection, projVis, circuitAnim, signColorMode, onPickStructure, onFocusCircuit, onFocusProjectionGroup) {
  // Populate the two collapsible bodies, not the panels themselves, so the
  // always-visible toggle headers (in index.html) are left untouched. If a section
  // authors a persistent actions container in the HTML (e.g. #structures-actions),
  // keep that exact node (it carries wireControls click handlers) as the sole
  // survivor and append the generated rows after it, so the buttons stay first;
  // otherwise the body is fully replaced. The structure rows go to the Structures
  // section; the projection / circuit / hypothetical rows to the Projections
  // section. One shared `reflect` (returned below) greys rows across both, so the
  // focus-state logic is not duplicated. (The arrow colour-mode switch lives up in
  // the Controls section now, so it is untouched by these rebuilds.)
  const structuresBody = document.getElementById("structures-body");
  const structuresActions = document.getElementById("structures-actions");
  if (structuresActions) structuresBody.replaceChildren(structuresActions);
  else structuresBody.replaceChildren();
  const projectionsBody = document.getElementById("projections-body");
  const projectionsActions = document.getElementById("projections-actions");
  if (projectionsActions) projectionsBody.replaceChildren(projectionsActions);
  else projectionsBody.replaceChildren();

  // Remember each structure row + the meshes it stands for, so the isolate state
  // can grey the ones that aren't selected. Headings are tracked too: clicking a
  // category heading toggles every structure under it at once.
  const structureRows = [];
  const groupHeadings = [];

  for (const [group, heading] of Object.entries(data.meta.groupLabels)) {
    const inGroup = data.structures.filter((s) => s.group === group);
    if (inGroup.length === 0) continue;
    const h = document.createElement("h2");
    h.textContent = heading;
    structuresBody.appendChild(h);

    // Collapse left/right twins by their base name (the hemisphere-stripped
    // label the generator emits, so this works in any language without parsing a
    // "Right "/"Left " prefix), gathering *both* hemispheres' meshes under that
    // one row so isolating it toggles the pair together.
    const byLabel = new Map();
    for (const s of inGroup) {
      const label = s.base_name || s.name;
      let entry = byLabel.get(label);
      if (!entry) {
        entry = { color: s.color, meshes: [] };
        byLabel.set(label, entry);
      }
      const mesh = meshById.get(s.id);
      if (mesh) entry.meshes.push(mesh);
    }
    const groupMeshes = [];
    for (const [label, entry] of byLabel) {
      const row = addLegendItem(structuresBody, entry.color, label);
      // Clicking the row toggles its structure(s) in the isolate/focus set AND,
      // when that click isolated it (not when it toggled it off), opens the
      // structure's detail tab, so a legend pick reads about the region like a 3D
      // click / search pick (which the user expects to "do both"). A toggle-off
      // opens nothing. The first hemisphere mesh stands for the pair's tab.
      row.classList.add("clickable");
      row.addEventListener("click", () => {
        selection.toggleIsolate(entry.meshes);
        if (onPickStructure && entry.meshes.some((m) => selection.isIsolated(m))) {
          onPickStructure(entry.meshes[0]);
        }
      });
      structureRows.push({ row, meshes: entry.meshes });
      groupMeshes.push(...entry.meshes);
    }
    // Clicking the category heading toggles the whole group (same on/off as
    // clicking each of its rows).
    h.classList.add("clickable");
    h.addEventListener("click", () => selection.toggleIsolate(groupMeshes));
    groupHeadings.push({ heading: h, meshes: groupMeshes });
  }

  // Neurotransmitters present in the data, one row each. Each is coloured by the
  // arrow `kind` it belongs to (the single colour source in arrows.js) and
  // labelled with the molecule plus that functional kind, e.g. "Glutamate
  // (excitatory)". Clicking a row isolates *only* that neurotransmitter: its
  // arrows + the structures they connect stay opaque, everything else fades (same
  // focus machinery as a circuit, via setCircuit). Clicking the active one clears
  // it. Rows are per-neurotransmitter (finer than kind) so when a kind later
  // carries more than one transmitter they split into their own rows for free.
  // Established pathways only: the tentative ones get their own section below, so
  // they never masquerade as an established row here. Grouping (per-transmitter or
  // per-sign) follows the active colour mode so the legend matches the arrows.
  const projRows = [];
  let activeProj = null;
  const established = arrows.filter((a) => !a.tentative);
  const projGroups = projectionGroups(established, data.meta, signColorMode);
  if (projGroups.length > 0) {
    const h = document.createElement("h2");
    h.textContent = t("legend.projections");
    projectionsBody.appendChild(h);
    for (const g of projGroups) {
      const row = addLegendItem(projectionsBody, g.color, g.label, true);
      // Endpoints of those arrows, kept opaque so an isolated group still reads as
      // connecting real regions rather than floating in a dimmed brain.
      const groupMeshes = [...new Set(g.arrows.flatMap((a) => [a.fromMesh, a.toMesh]))];
      row.classList.add("clickable");
      // The sourced data record for this row's grouping (kind / sign), so the
      // click can open its detail panel + tab. Resolved by the row's dataKey.
      const groupRecord = data.projectionGroupsByKey
        && data.projectionGroupsByKey.get(g.dataKey);
      row.addEventListener("click", () => {
        if (activeProj === g.key) selection.clear();
        else if (onFocusProjectionGroup && groupRecord) onFocusProjectionGroup(groupRecord);
        // Fallback (no panel record): the old focus-only behaviour.
        else selection.setCircuit(groupMeshes, g.arrows);
      });
      projRows.push({ row, key: g.key, arrowSet: new Set(g.arrows) });
    }
  }

  // Circuits: each entry resolves to its structures' meshes and the arrows
  // *between* them (both endpoints in the set). Clicking one isolates exactly
  // that circuit (its structures + its internal pathways opaque, the rest faint);
  // clicking the active one again clears it.
  const circuitRows = [];
  let activeCircuitId = null;
  if (data.circuits && data.circuits.length > 0) {
    const h = document.createElement("h2");
    h.textContent = t("legend.circuits");
    projectionsBody.appendChild(h);
    for (const circuit of data.circuits) {
      const meshes = circuit.structures.map((id) => meshById.get(id)).filter(Boolean);
      const meshSet = new Set(meshes);
      const circuitArrows = arrows.filter(
        (a) => meshSet.has(a.fromMesh) && meshSet.has(a.toMesh));
      // Neutral swatch (a circuit has no single colour) drawn as a thin bar.
      const row = addLegendItem(projectionsBody, "#b0b0b0", circuit.name, true);
      row.classList.add("clickable");
      const entry = { row, id: circuit.id, meshes, meshSet, arrows: circuitArrows };
      row.addEventListener("click", () => {
        if (activeCircuitId === circuit.id) selection.clear();
        else if (onFocusCircuit) onFocusCircuit(circuit);
        else {
          // Fallback (no panel callback): isolate the circuit + start its pulse,
          // the old focus-only behaviour. Order matters: setCircuit fires the
          // focus-change watcher (which stops any prior animation) before play()
          // begins this one. The watcher stops these pulses on the next change.
          selection.setCircuit(meshes, circuitArrows);
          if (circuitAnim) circuitAnim.play(circuitArrows);
        }
      });
      circuitRows.push(entry);
    }
  }

  // Hypothetical / speculative pathways (projection.tentative): their own
  // section, off by default, drawn as dotted arrows. Clicking the row reveals or
  // hides just these (via projVis, separate from the global "Hide projections"
  // button which hides everything). Kept out of the per-transmitter rows above so
  // they never read as established connections.
  const tentativeArrows = arrows.filter((a) => a.tentative);
  if (tentativeArrows.length > 0 && projVis) {
    const h = document.createElement("h2");
    h.textContent = t("legend.hypothetical");
    projectionsBody.appendChild(h);
    const count = new Set(tentativeArrows.map((a) => a.projection.label)).size;
    // A dotted swatch (a repeating gradient, so no extra CSS), echoing the dotted
    // arrows; neutral grey since these span several transmitter colours.
    const dotted =
      "repeating-linear-gradient(90deg, #b0b0b0 0 5px, transparent 5px 9px)";
    const row = addLegendItem(
      projectionsBody, dotted, `${t("legend.showSpeculative")} (${count})`, true);
    row.classList.add("clickable");
    row.title = t("legend.hypotheticalHint");
    row.addEventListener("click", () => {
      const show = !projVis.tentativeShown;
      projVis.setTentativeShown(show);
      row.classList.toggle("selected", show);
      row.lastChild.textContent =
        `${show ? t("legend.hideSpeculative") : t("legend.showSpeculative")} (${count})`;
    });
  }

  // Reflect the isolate set onto the legend: the isolated rows stay lit, the
  // rest grey out. `null` (nothing isolated) clears both states. A heading lights
  // only when its whole group is isolated; a circuit row lights only when the
  // isolate set is *exactly* that circuit (so toggling a structure unlights it);
  // a neurotransmitter row lights only when the pinned-arrow set is exactly that
  // transmitter's arrows. `focusedArrows` is the pinned-arrow set (empty unless a
  // circuit/neurotransmitter is focused).
  return function reflect(isolated, focusedArrows) {
    // Detect a projection-group focus first: the pinned-arrow set is exactly one
    // group's arrows. Such a focus dims every structure (only that group's arrows
    // + endpoints stay opaque in the scene), so its structure/heading rows grey
    // out rather than lighting up; that lit-row noise only makes sense for a
    // circuit.
    const matchesGroup = (arrowSet) => arrowSet.size > 0 && focusedArrows
      && focusedArrows.size === arrowSet.size
      && [...arrowSet].every((a) => focusedArrows.has(a));
    activeProj = null;
    for (const { key, arrowSet } of projRows) if (matchesGroup(arrowSet)) activeProj = key;
    const projFocus = activeProj !== null;

    for (const { row, meshes } of structureRows) {
      const selected = Boolean(isolated) && !projFocus && meshes.some((m) => isolated.has(m));
      row.classList.toggle("selected", selected);
      row.classList.toggle("dimmed", Boolean(isolated) && !selected);
    }
    for (const { row, arrowSet } of projRows) {
      const selected = matchesGroup(arrowSet);
      row.classList.toggle("selected", selected);
      row.classList.toggle("dimmed", Boolean(isolated) && !selected);
    }
    for (const { heading, meshes } of groupHeadings) {
      const all = !projFocus && isolated && meshes.length > 0 && meshes.every((m) => isolated.has(m));
      const any = !projFocus && isolated && meshes.some((m) => isolated.has(m));
      heading.classList.toggle("selected", Boolean(all));
      heading.classList.toggle("dimmed", Boolean(isolated) && !any);
    }
    activeCircuitId = null;
    for (const { row, id, meshes, meshSet } of circuitRows) {
      const selected = Boolean(isolated) && meshes.length > 0
        && isolated.size === meshSet.size && meshes.every((m) => isolated.has(m));
      if (selected) activeCircuitId = id;
      row.classList.toggle("selected", selected);
      row.classList.toggle("dimmed", Boolean(isolated) && !selected);
    }
  };
}

/**
 * Build the static Legend "key" (#legend-body): a small, non-interactive colour /
 * symbol legend for the 3D scene's encodings that have no label in the interactive
 * sections, so a first-time viewer can decode what a glowing gem dot or a dotted
 * arrow means. Deliberately *not* a copy of the Projections rows (the arrow
 * colours live there) nor the About provenance key; only the otherwise-unlabeled
 * encodings:
 *   - expression "gem" dots over a focused receptor / target, coloured by its
 *     excit / inhib / modulatory sign;
 *   - the per-drug effect dots + surface wash, coloured boost / block / modulate;
 *   - a speculative pathway, drawn as a dotted arrow.
 * Colours come from the dataset's meta (signColors/signLabels, drugEffectColors/
 * drugEffectLabels), so the key can never drift from what the scene draws.
 * @param {import("./data.js").BrainData} data
 */
/**
 * Fill `el` with `str`, rendering `*emphasis*` spans as <em>. Builds real text +
 * <em> DOM nodes (never innerHTML), so it is injection-safe for any string.
 */
function setInlineEmphasis(el, str) {
  el.replaceChildren();
  // Odd-indexed capture groups are the emphasized runs.
  (str || "").split(/\*([^*]+)\*/g).forEach((part, i) => {
    if (i % 2 === 1) {
      const em = document.createElement("em");
      em.textContent = part;
      el.appendChild(em);
    } else if (part) {
      el.appendChild(document.createTextNode(part));
    }
  });
}

function buildLegendKey(data) {
  const body = document.getElementById("legend-body");
  if (!body) return;
  body.replaceChildren();
  const meta = data.meta || {};

  // A heading + a muted one-line caption + its swatches.
  const section = (headingKey, captionKey, entries) => {
    if (entries.length === 0) return;
    const h = document.createElement("h2");
    h.textContent = t(headingKey);
    body.appendChild(h);
    const cap = document.createElement("p");
    cap.className = "legend-caption";
    setInlineEmphasis(cap, t(captionKey));
    body.appendChild(cap);
    for (const { color, label, line } of entries) {
      addLegendItem(body, color, label, Boolean(line));
    }
  };

  // Expression dots (receptors & targets): one swatch per excit/inhib/modulatory
  // sign, the same colours the dots are drawn in.
  section("legendKey.dots", "legendKey.dotsDesc",
    Object.entries(meta.signLabels || {}).map(([sign, label]) => ({
      color: (meta.signColors || {})[sign] || "#fff", label,
    })));

  // Drug effect dots + wash: boost / block / modulate, in their effect colours.
  section("legendKey.effects", "legendKey.effectsDesc",
    Object.entries(meta.drugEffectColors || {}).map(([effect, color]) => ({
      color, label: (meta.drugEffectLabels || {})[effect] || effect,
    })));

  // Drug flow overlay: beads ride the ascending pathways of the transmitter
  // system(s) the drug engages. One line swatch per distinct flow-capable kind
  // (the values of meta.systemFlowKinds), in that kind's projection colour, so
  // the key names exactly the fans that can light up. Rendered as a line to echo
  // that these are pathways, not regions.
  const flowKinds = [...new Set(Object.values(meta.systemFlowKinds || {}))];
  section("legendKey.flow", "legendKey.flowDesc",
    flowKinds.map((kind) => ({
      color: (meta.projectionColors || {})[kind] || "#fff",
      label: (meta.kindLabels || {})[kind] || kind,
      line: true,
    })));

  // Speculative pathway: a dotted swatch echoing the dotted arrows (drawn as a
  // thin line, like the projection rows). The caption is the heading itself, so
  // pass the heading text and an empty caption row is avoided by reusing it.
  const dotted = "repeating-linear-gradient(90deg, #b0b0b0 0 5px, transparent 5px 9px)";
  const hP = document.createElement("h2");
  hP.textContent = t("legendKey.pathways");
  body.appendChild(hP);
  addLegendItem(body, dotted, t("legendKey.speculative"), true);
}

/**
 * Browser-style detail tabs at the top of the bottom-left panel. The first tab,
 * **Settings**, is pinned (always first, never scrolled away) and shows the
 * controls pane; every other tab is one opened detail (a structure / connection /
 * receptor / target / drug), shown in the Details pane. The bar ships hidden and
 * appears once the first detail is opened.
 *
 * This controller only owns the *tab strip + which pane shows*; it does NOT know
 * how to render a detail or apply its 3D focus. `openDetail({key,title,reopen})`
 * registers/activates a tab (called by the select* layer after it has rendered +
 * focused), and clicking a tab calls its `reopen()` (which re-renders #info-body
 * and re-applies the focus, then calls openDetail again to mark it active). So a
 * detail's content + scene state always match the active tab, with no duplicated
 * render logic.
 *
 * Interactions: click a tab to activate it, click its × to close it, long-press a
 * tab then drag to reorder it; the strip scrolls (wheel on desktop, touch-drag on
 * mobile) when the tabs overflow the narrow panel. The strip is touch-action:none
 * so a tab's long-press can't be hijacked by the browser's native pan (which would
 * fire pointercancel mid-hold and kill the reorder on touch); the drag-scroll for a
 * swipe-before-hold is therefore driven here in JS. Closing the active tab falls
 * back to its neighbour (re-applying that one's focus) or, if it was the last
 * detail, to Settings + `onEmpty()` (which clears the 3D selection).
 * @returns {{openDetail:Function, showSettings:()=>void, setOnEmpty:Function}}
 */
function createPanelTabs() {
  const bar = document.getElementById("panel-tabs");
  const tabSettings = document.getElementById("tab-settings");
  const strip = document.getElementById("detail-tabs");
  const settingsPane = document.getElementById("settings-pane");
  const detailsPane = document.getElementById("details-pane");
  const controlsToggle = document.getElementById("controls-toggle");
  const controlsBody = document.getElementById("controls-body");

  const MAX_TABS = 12; // bound the strip; the oldest inactive tab drops past this
  const LONG_PRESS_MS = 450; // hold this long (roughly still) to start a reorder
  const MOVE_CANCEL = 8; // px of movement before the long-press fires => a scroll

  let openTabs = []; // [{ key, title, reopen }], left-to-right order
  let activeKey = null; // active detail key, or null when Settings is shown
  let onEmpty = () => {}; // run when the last detail tab is closed (clears the 3D)
  let press = null; // in-flight pointer press (long-press / reorder bookkeeping)
  let suppressClick = false; // a reorder drag must not also activate the tab

  // Show the Settings or Details pane and keep the bar's visibility + the pinned
  // Settings tab's active state in sync. The bar hides entirely with no detail
  // tabs open (back to the plain Settings view).
  const showPane = (details) => {
    settingsPane.hidden = details;
    detailsPane.hidden = !details;
    bar.hidden = openTabs.length === 0;
    tabSettings.classList.toggle("active", !details);
    tabSettings.setAttribute("aria-selected", String(!details));
  };

  const expandPanel = () => {
    // The detail must be visible, so make sure the panel body is expanded (the
    // ResizeObserver in wireControls then re-runs the small-screen pan-aside).
    if (controlsToggle.getAttribute("aria-expanded") !== "true") {
      controlsToggle.setAttribute("aria-expanded", "true");
      controlsBody.hidden = false;
    }
  };

  // Rebuild the detail-tab buttons from openTabs (the array is the source of
  // truth). Cheap: a handful of tabs at most.
  const render = () => {
    strip.textContent = "";
    for (const tab of openTabs) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "detail-tab" + (tab.key === activeKey ? " active" : "");
      btn.dataset.key = tab.key;
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-selected", String(tab.key === activeKey));
      const label = document.createElement("span");
      label.className = "detail-tab-label";
      label.textContent = tab.title;
      label.title = tab.title; // full name on hover (the label is ellipsized)
      const close = document.createElement("span");
      close.className = "detail-tab-close";
      close.textContent = "×";
      close.setAttribute("aria-label", t("panel.closeTab"));
      btn.append(label, close);
      strip.appendChild(btn);
    }
    bar.hidden = openTabs.length === 0;
    tabSettings.classList.toggle("active", activeKey === null);
  };

  const scrollActiveIntoView = () => {
    const el = strip.querySelector(".detail-tab.active");
    if (el) el.scrollIntoView({ inline: "nearest", block: "nearest" });
  };

  // Re-show a tab's detail: its reopen() re-renders + re-applies the 3D focus and
  // calls openDetail(key), which marks it active and shows the Details pane.
  const activate = (key) => {
    const tab = openTabs.find((tb) => tb.key === key);
    if (tab) tab.reopen();
  };

  const closeTab = (key) => {
    const idx = openTabs.findIndex((tb) => tb.key === key);
    if (idx === -1) return;
    openTabs.splice(idx, 1);
    if (key !== activeKey) { render(); return; } // 3D unchanged; just drop the chip
    if (openTabs.length) {
      // Fall back to the neighbour that slid into this slot (or the new last one),
      // re-applying its focus so the scene matches the now-active tab.
      activate(openTabs[Math.min(idx, openTabs.length - 1)].key);
    } else {
      activeKey = null;
      showPane(false);
      onEmpty(); // nothing left selected: clear the 3D focus
      render();
    }
  };

  // ----- strip interactions (event-delegated on the scroll container) -----
  // Click: the × closes, anywhere else activates (unless a reorder just ran).
  strip.addEventListener("click", (e) => {
    if (suppressClick) { suppressClick = false; return; }
    const btn = e.target.closest(".detail-tab");
    if (!btn) return;
    if (e.target.closest(".detail-tab-close")) closeTab(btn.dataset.key);
    else activate(btn.dataset.key);
  });

  // Long-press a tab to lift it into a reorder drag; a move before the press
  // fires is a scroll instead, so we bow out and let the strip scroll natively.
  strip.addEventListener("pointerdown", (e) => {
    const btn = e.target.closest(".detail-tab");
    if (!btn || e.target.closest(".detail-tab-close")) return;
    if (e.pointerType === "mouse" && e.button !== 0) return;
    press = { key: btn.dataset.key, btn, x: e.clientX, y: e.clientY,
      pointerId: e.pointerId, dragging: false, moved: false };
    press.timer = setTimeout(() => {
      if (!press) return;
      press.dragging = true;
      press.btn.classList.add("dragging");
      // Take the pointer + stop the browser scrolling so the drag is ours.
      strip.style.touchAction = "none";
      try { press.btn.setPointerCapture(press.pointerId); } catch (_) {}
    }, LONG_PRESS_MS);
  });
  strip.addEventListener("pointermove", (e) => {
    if (!press) return;
    if (!press.dragging) {
      // Moved before the long-press fired: a swipe, so scroll the strip ourselves
      // (it is touch-action:none, so the browser no longer pans it natively, which
      // is exactly what used to fire pointercancel mid-hold and kill the reorder on
      // touch). Capture the pointer so the moves keep coming as tabs slide under it.
      if (!press.scrolling &&
          Math.hypot(e.clientX - press.x, e.clientY - press.y) > MOVE_CANCEL) {
        clearTimeout(press.timer);
        press.scrolling = true;
        press.lastX = e.clientX;
        try { press.btn.setPointerCapture(press.pointerId); } catch (_) {}
      }
      if (press.scrolling) {
        strip.scrollLeft -= e.clientX - press.lastX;
        press.lastX = e.clientX;
        press.moved = true;
        e.preventDefault();
      }
      return;
    }
    e.preventDefault();
    press.moved = true;
    // Insert the dragged chip before the first sibling whose midpoint is right of
    // the pointer (the canonical drag-to-reorder move); the element keeps its
    // identity + capture, so we reorder the DOM live and sync the array on drop.
    const after = [...strip.querySelectorAll(".detail-tab:not(.dragging)")].find(
      (s) => {
        const r = s.getBoundingClientRect();
        return e.clientX < r.left + r.width / 2;
      });
    if (after) strip.insertBefore(press.btn, after);
    else strip.appendChild(press.btn);
  });
  const endPress = () => {
    if (!press) return;
    clearTimeout(press.timer);
    if (press.dragging) {
      press.btn.classList.remove("dragging");
      strip.style.touchAction = "";
      try { press.btn.releasePointerCapture(press.pointerId); } catch (_) {}
      // Reorder openTabs to match the live DOM order, then rebuild cleanly.
      const order = [...strip.querySelectorAll(".detail-tab")].map((b) => b.dataset.key);
      openTabs.sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
      if (press.moved) {
        // The browser fires a synthetic click on the dragged tab right after this
        // pointerup; swallow only THAT click, then clear the flag on the next tick
        // so a later, unrelated tab click is never eaten.
        suppressClick = true;
        setTimeout(() => { suppressClick = false; }, 0);
      }
      render();
    } else if (press.scrolling) {
      try { press.btn.releasePointerCapture(press.pointerId); } catch (_) {}
      // A drag-scroll on a tab must not also activate it on the trailing click.
      suppressClick = true;
      setTimeout(() => { suppressClick = false; }, 0);
    }
    press = null;
  };
  strip.addEventListener("pointerup", endPress);
  strip.addEventListener("pointercancel", endPress);

  // Wheel over the strip scrolls it horizontally (the desktop "scroll through
  // tabs"); touch gets native horizontal scroll via touch-action: pan-x (CSS).
  strip.addEventListener("wheel", (e) => {
    if (!e.deltaY) return;
    strip.scrollLeft += e.deltaY;
    e.preventDefault();
  }, { passive: false });

  // Return to the pinned Settings tab (active = none), keeping every detail tab.
  const selectSettings = () => {
    activeKey = null;
    showPane(false);
    render();
  };
  tabSettings.addEventListener("click", selectSettings);

  return {
    /**
     * Register (or re-activate) the tab for a detail. Called by the select* layer
     * after it has rendered #info-body + applied the 3D focus. `key` dedupes (one
     * tab per thing), `title` is the chip label, `reopen` re-runs that select* so
     * clicking the tab restores both the panel and the scene.
     */
    openDetail({ key, title, reopen }) {
      let tab = openTabs.find((tb) => tb.key === key);
      if (tab) {
        tab.title = title;
        tab.reopen = reopen;
      } else {
        tab = { key, title, reopen };
        openTabs.push(tab);
        if (openTabs.length > MAX_TABS) {
          const drop = openTabs.findIndex((tb) => tb.key !== key && tb.key !== activeKey);
          if (drop !== -1) openTabs.splice(drop, 1);
        }
      }
      activeKey = key;
      expandPanel();
      showPane(true);
      render();
      scrollActiveIntoView();
    },
    /**
     * Switch to the pinned Settings tab without closing any detail tabs (they stay
     * in the strip as history). Used by search (its box lives in the Settings
     * pane) and by an empty-space click / deselect.
     */
    showSettings() {
      selectSettings();
    },
    /**
     * Close the currently active detail tab (falling back to a neighbour or
     * Settings, like its × button). Returns true when a detail was active and got
     * closed, false when Settings was active (nothing to close) so the caller (Esc)
     * can fall through to other behaviour.
     */
    closeActive() {
      if (activeKey === null) return false;
      closeTab(activeKey);
      return true;
    },
    /**
     * Cycle the active tab one step (`+1` next, `-1` previous) through the pinned
     * Settings tab plus the open detail tabs, wrapping around. Landing on a detail
     * re-applies its 3D focus (same as clicking it); landing on Settings returns
     * to the controls. Returns false (nothing to cycle) when only Settings exists,
     * so the caller can leave the Tab key's default focus move intact.
     */
    cycle(dir) {
      if (openTabs.length === 0) return false;
      const keys = [null, ...openTabs.map((tb) => tb.key)]; // Settings first, then details
      const at = keys.indexOf(activeKey);
      const target = keys[(at + dir + keys.length) % keys.length];
      if (target === null) selectSettings();
      else activate(target);
      return true;
    },
    /** Close every open detail tab, returning to Settings (fires onEmpty once the
     *  last one goes, clearing the 3D focus + the URL hash). No-op when none open. */
    closeAll() {
      if (!openTabs.length) return false;
      // Drop them all, then let the shared close path settle the empty state.
      openTabs.length = 0;
      activeKey = null;
      showPane(false);
      onEmpty();
      render();
      return true;
    },
    /** Set the callback run when the last detail tab is closed (clears the 3D). */
    setOnEmpty(fn) { onEmpty = fn; },
    /** The active detail tab's key (`<kind>:<id>`), or null when Settings is shown.
     *  Used to build the shareable deep link that mirrors the focus into the URL. */
    activeKey() { return activeKey; },
  };
}

// A drug binding's representative Ki (its median), or Infinity when unmeasured. The
// single "how hard does this drug grip this target" ranking key, shared by the info
// panel (the drug's "Acts on" order, each system's strongest binding) and the target
// legend's affinity sort, so every affinity ordering agrees.
const bindingKi = (b) =>
  b.ki && typeof b.ki.median === "number" ? b.ki.median : Infinity;

/**
 * Build the detail panel renderer. The panel is a **node view**: each show*()
 * method renders one node (a connection / structure / receptor / target / drug /
 * circuit / projection group) plus the nodes linked to it (a receptor's "Found in"
 * regions + interacting drugs, a drug's target bindings, a structure's pathways,
 * ...), each linked node clickable to navigate to it. See the Nodes section of
 * CLAUDE.md. It is pure rendering: opening the matching tab + applying the 3D focus
 * is the caller's job (the select* layer in main(), which calls openDetailTab), so
 * this is reused unchanged whether a node is first picked or re-shown via its tab.
 * @param {import("./data.js").BrainData} data
 */

// Only one tooltip is pinned at a time across the whole UI: opening one closes
// whichever was open, so tapping a second pill / bar dismisses the first instead of
// stacking popups. Holds the open tip's `close` (so its scroll/resize listeners are
// torn down too, not just its `.show` class).
let _openTip = null;

// The nearest ancestor that establishes a containing block for a position:fixed
// descendant (a transform / filter / backdrop-filter / perspective / will-change /
// paint-contain), or null if none (then fixed is viewport-relative). The panel
// #controls carries a backdrop-filter, so a fixed tooltip is offset by it; we walk
// this generically rather than hardcoding #controls.
function fixedContainingBlock(node) {
  for (let n = node.parentElement; n && n !== document.documentElement; n = n.parentElement) {
    const s = getComputedStyle(n);
    const bf = s.backdropFilter || s.webkitBackdropFilter;
    if ((s.transform && s.transform !== "none") ||
        (s.filter && s.filter !== "none") ||
        (bf && bf !== "none") ||
        (s.perspective && s.perspective !== "none") ||
        (s.willChange && /transform|filter|perspective/.test(s.willChange)) ||
        (s.contain && /paint|layout|strict|content/.test(s.contain))) {
      return n;
    }
  }
  return null;
}

/**
 * Attach a hover/tap tooltip to `trigger`. The bubble is position:fixed just above
 * the trigger, clamped to the viewport, and lives on <body> while shown (so a dimmed
 * ancestor row can't bleed opacity into it, an overflow can't clip it, and you can
 * move onto the bubble to read/select its text). Shows on hover/focus (pointer +
 * keyboard) and is pinned on click/tap: on a touch screen `:hover` never fires, so
 * the click-toggle is the sole path (one tap shows, tap again or tap elsewhere
 * dismisses); on a pointer device a click pins it so its text stays selectable.
 *
 * Shared by the info panel's provenance pills (`opts.wrap` wraps the trigger in a
 * `.help-icon` span and returns that wrapper, so an inline pill anchors to itself)
 * and the sourcing coverage bars (block elements, attached in place with a raised
 * `opts.zIndex` so the bubble clears the #sourcing-modal backdrop).
 * @returns {HTMLElement} the wrapper when `opts.wrap`, else `trigger` itself.
 */
function attachTip(trigger, tipText, { wrap = false, zIndex = null } = {}) {
  const host = wrap ? document.createElement("span") : trigger;
  if (wrap) { host.className = "help-icon"; host.append(trigger); }
  const tip = document.createElement("span");
  tip.className = "help-tip";
  tip.setAttribute("role", "tooltip");
  // `tipText` is usually a string (set as textContent). It may instead be a Node
  // (e.g. a fragment carrying a clickable source link): appended live so the link
  // stays interactive. The node is consumed once here; it then lives in this bubble
  // permanently, moving in/out of <body> with it on open/close.
  if (tipText instanceof Node) tip.appendChild(tipText);
  else tip.textContent = tipText;
  if (zIndex != null) tip.style.zIndex = String(zIndex);
  if (!wrap) trigger.style.cursor = "help";
  let pinned = false, hideTimer = 0;
  const place = () => {
    const r = trigger.getBoundingClientRect();
    const m = 6, gap = 4;
    // Choose the vertical side (above default, matching the arrow-less convention),
    // then cap the bubble to that side's free space so a long tooltip scrolls inside
    // itself (overflow-y:auto) instead of running off-screen and being cropped.
    tip.style.maxHeight = "none";            // measure the natural height first
    const natural = tip.offsetHeight;
    // Free space each side, capped to the viewport (a partly-scrolled trigger can push
    // r.top/r.bottom past the edges, which would otherwise let maxHeight exceed the
    // screen and re-crop a long tooltip).
    const vLimit = window.innerHeight - 2 * m;
    const spaceAbove = Math.min(r.top - m - gap, vLimit);
    const spaceBelow = Math.min(window.innerHeight - r.bottom - m - gap, vLimit);
    let below;
    if (natural <= spaceAbove) below = false;        // fits above -> above
    else if (natural <= spaceBelow) below = true;    // else fits below -> below
    else below = spaceBelow > spaceAbove;            // fits neither -> roomier side (scrolls)
    const avail = Math.max(0, Math.floor(below ? spaceBelow : spaceAbove));
    tip.style.maxHeight = `${avail}px`;
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let left = r.left + r.width / 2 - tw / 2;
    left = Math.max(m, Math.min(left, window.innerWidth - tw - m));
    let top = below ? r.bottom + gap : r.top - th - gap;
    top = Math.max(m, Math.min(top, window.innerHeight - th - m)); // never off-screen
    // With the bubble in <body> there is normally no fixed-positioning containing
    // block (offsets zero), but keep the generic subtraction in case a transformed /
    // filtered ancestor ever forms one.
    const cb = fixedContainingBlock(tip);
    const cbRect = cb ? cb.getBoundingClientRect() : null;
    const ox = cb ? cbRect.left - cb.scrollLeft : 0;
    const oy = cb ? cbRect.top - cb.scrollTop : 0;
    tip.style.left = `${Math.round(left - ox)}px`;
    tip.style.top = `${Math.round(top - oy)}px`;
  };
  const reposition = () => {
    if (!trigger.isConnected) { close(); return; }
    if (tip.classList.contains("show")) place();
  };
  // A scroll INSIDE the bubble (reading a long, height-capped tooltip) must not
  // reposition it: place() re-measures the natural height, which would fight the
  // user's scroll. Only an outside scroll (the page/panel moving) repositions.
  const onScroll = (e) => {
    if (e.target === tip || (e.target instanceof Node && tip.contains(e.target))) return;
    reposition();
  };
  const onDocPointer = (e) => {
    if (host.contains(e.target) || tip.contains(e.target)) return;
    close();
  };
  const open = () => {
    clearTimeout(hideTimer);
    if (_openTip && _openTip !== close) _openTip(); // close any other open tip
    _openTip = close;
    if (!tip.isConnected) document.body.appendChild(tip);
    tip.classList.add("show");
    place();
    // Re-place after this frame: tapping a button can focus-scroll it into view
    // *after* the click handler runs, which would otherwise strand the bubble.
    requestAnimationFrame(place);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", reposition);
    document.addEventListener("pointerdown", onDocPointer, true);
  };
  const close = () => {
    clearTimeout(hideTimer);
    pinned = false;
    if (_openTip === close) _openTip = null;
    tip.classList.remove("show");
    tip.remove();
    window.removeEventListener("scroll", onScroll, true);
    window.removeEventListener("resize", reposition);
    document.removeEventListener("pointerdown", onDocPointer, true);
  };
  const scheduleHide = () => {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      if (pinned || trigger.matches(":hover") || tip.matches(":hover")) return;
      close();
    }, 160);
  };
  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    if (pinned) close(); else { pinned = true; open(); }
  });
  const canHover = !window.matchMedia ||
    window.matchMedia("(hover: hover)").matches;
  if (canHover) {
    trigger.addEventListener("mouseenter", open);
    trigger.addEventListener("mouseleave", scheduleHide);
    trigger.addEventListener("focus", open);
    trigger.addEventListener("blur", scheduleHide);
    tip.addEventListener("mouseenter", () => clearTimeout(hideTimer));
    tip.addEventListener("mouseleave", scheduleHide);
  }
  return host;
}

function createInfoPanel(data) {
  const body = document.getElementById("info-body");
  const nameOf = (id) => data.byId.get(id)?.name || id;
  // Hemisphere-stripped name ("Frontal lobe", not "Right frontal lobe"): used by
  // every pathway list so left/right twins collapse to one row (see pathwayList).
  const baseNameOf = (id) => data.byId.get(id)?.base_name || nameOf(id);

  // Set by the caller (onConnection): what to do when a connection row in a
  // structure panel is clicked. The panel only knows projections, so the caller
  // maps the projection to its arrow and does the framing/halo/connection-panel.
  let onConnectionPick = () => {};
  // Set by the caller (onTarget): what to do when a binding row in a drug panel is
  // clicked. The panel hands back the resolved target entry; the caller focuses it
  // exactly like its "Receptors & targets" legend row.
  let onTargetPick = () => {};
  // Set by the caller (onStructure): what to do when a region row in a receptor /
  // target panel's "Found in" list is clicked. The panel hands back the structure
  // *base* id; the caller resolves it to a mesh and jumps to that structure.
  let onStructurePick = () => {};
  // Set by the caller (onDrug): what to do when a drug row in a receptor / target
  // panel's "Interacting drugs" list is clicked. The panel hands back the drug
  // record; the caller focuses it exactly like its Drugs legend row / search pick.
  let onDrugPick = () => {};
  // Set by the caller (onProjectionGroup): what to do when a projection-group row in
  // a drug panel's "Projections affected" list is clicked. The panel hands back the
  // group record; the caller focuses it exactly like its Projections legend row.
  let onProjectionGroupPick = () => {};
  // Set by the caller (onSearch): run a search query. A drug panel's clickable
  // Class / Nomenclature values hand back a `field:"value"` query string; the caller
  // opens the search box pre-filled with it (see wireToolbar.openSearchWithQuery).
  let onSearchPick = () => {};
  // Set by the caller (onImage): pop a panel illustration up large. The panel hands
  // back (src, alt, {invert}); the caller shows it in the image lightbox.
  let onImagePick = () => {};
  // Resolve a drug binding's `target` key to its merged-list entry, so a binding
  // row can focus that target (a receptor entry shares its id; a non-receptor one
  // its drug_targets key). Only focusable entries become clickable.
  const targetById = new Map(data.targets.map((tg) => [tg.id, tg]));
  const drugById = new Map((data.drugs || []).map((d) => [d.id, d]));

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  // True when a structure *base* id maps to a modeled structure (the base itself
  // for a midline form, or its _R / _L hemispheres), i.e. it is reachable in the
  // atlas and so can be jumped to. tools/check_data.py enforces that every
  // receptor / target location resolves, so an unresolved base should not occur in
  // shipped data; the panel still degrades to plain (non-clickable) text if one does.
  // Resolve a structure *base* id to its modeled record: the base itself (a midline
  // form), else its _R / _L hemisphere, else null. The one place the hemisphere-suffix
  // fallback lives, so baseResolves and groupOfBase can't drift.
  const resolveBase = (base) =>
    data.byId.get(base) || data.byId.get(`${base}_R`)
      || data.byId.get(`${base}_L`) || null;
  const baseResolves = (base) => !!resolveBase(base);

  // The anatomical group (lobe / basal_ganglia / ...) a structure *base* belongs to,
  // or null if it doesn't resolve. Lets the "Found in" list group its regions the
  // same way the Structures legend does.
  const groupOfBase = (base) => resolveBase(base)?.group ?? null;

  // One "Found in" region row: the name (clickable -> jump when the base resolves)
  // plus, when `meta` is given, its own per-region provenance pill (since "found in
  // region B" is graded per region, separate from the mechanism/type pill above).
  const locationRow = (name, base, meta) => {
    const li = el("li");
    li.appendChild(el("span", "loc-name", name));
    // A non-human expression claim (the source was checked in rat/mouse/monkey,
    // not human) is flagged with a small amber tag, the same convention as the Ki
    // chip; a human (or unsourced) row shows none. The full assay species is also
    // in the provenance pill's tooltip below.
    if (meta && meta.nonHuman) {
      const tag = el("span", "loc-species",
        t("receptor.speciesTag", { species: speciesLabel(meta.species) }));
      tag.title = t("receptor.speciesTip", { species: speciesLabel(meta.species) });
      li.appendChild(tag);
    }
    if (base && baseResolves(base)) {
      li.classList.add("clickable");
      li.addEventListener("click", () => onStructurePick(base));
    }
    if (meta) {
      const tip = meta.sources && meta.sources.length
        ? sourcesTip(meta.sources) : t("receptor.locUnsourced");
      li.appendChild(makeProvenancePill(meta.provenance, tip));
    }
    return li;
  };

  // The "Found in" region list shared by showReceptor / showTarget: parallel arrays
  // of display names + their base ids (+ optional per-region provenance `info`).
  // Rows are grouped under anatomical-group headings in the SAME order as the
  // Structures legend (data.meta.groupLabels key order), so the list reads like that
  // panel and the extra vertical spacing keeps the provenance pills from crowding.
  // Bases that don't resolve to a group fall into a trailing "other" bucket (with a
  // heading only when there are also real groups; an all-unresolved list stays flat).
  const locationList = (names, bases, info) => {
    const buckets = new Map(); // group key (or null) -> [{name, base, meta}]
    names.forEach((name, i) => {
      const base = bases && bases[i];
      const g = base ? groupOfBase(base) : null;
      if (!buckets.has(g)) buckets.set(g, []);
      buckets.get(g).push({ name, base, meta: info && info[i] });
    });
    const order = [...Object.keys(data.meta.groupLabels), null]
      .filter((g) => buckets.has(g));
    const container = el("div", "loc-groups");
    for (const g of order) {
      if (g !== null) {
        container.appendChild(el("h4", "loc-group-label", data.meta.groupLabels[g]));
      } else if (order.length > 1) {
        container.appendChild(el("h4", "loc-group-label", t("receptor.foundOther")));
      }
      const ul = el("ul");
      for (const { name, base, meta } of buckets.get(g)) {
        ul.appendChild(locationRow(name, base, meta));
      }
      container.appendChild(ul);
    }
    return container;
  };

  // One route endpoint (a structure id) for the connection panel's route line: its
  // name, made clickable to jump to (and isolate) that structure when the id
  // resolves to a modeled mesh, exactly like a "Found in" region row. A non-
  // resolving id degrades to plain text.
  const endpointEl = (id) => {
    const name = nameOf(id);
    if (id && baseResolves(id)) {
      const b = el("button", "conn-endpoint", name);
      b.type = "button";
      b.addEventListener("click", () => onStructurePick(id));
      return b;
    }
    return el("span", null, name);
  };

  // withTip wraps an inline provenance pill in a .help-icon span and returns that
  // wrapper (so the pill anchors to itself). The whole hover/tap tooltip mechanism
  // lives in the module-level attachTip (shared with the sourcing coverage bars).
  const withTip = (trigger, tipText) => attachTip(trigger, tipText, { wrap: true });

  // Per-source provenance pill (how trustworthy the source's attribution is):
  // grey "?" = LLM-only (may be hallucinated), yellow "~" = the LLM had the source
  // document, green "✓" = quote-checked + agreed by a second LLM. The colour is a
  // `.src-prov-<level>` CSS class. A falsy / unknown level is the "no source yet"
  // case and renders the red ✕ NOSOURCE pill (`.src-todo`) instead. The pill is a
  // <button> so a tap pins its explanatory tooltip on touch (via withTip). Each
  // pill's tooltip explains its own grade, and the About panel ("Sources &
  // provenance") carries the full grade key, so there is no separate blanket "?"
  // caveat. The three stored grades come from the data (generate_data.py
  // PROVENANCE_LEVELS); `wikipedia` is a viewer-only presentation for a live-fetched
  // Wikipedia lead (a runtime read, not a stored node grade), green because it is a
  // verbatim programmatic extract of an inspectable source, so it can't drift from
  // Wikipedia. Only the glyph + tooltip live here.
  const PROVENANCE_PILLS = {
    llm: { glyph: "?", tip: "info.provLlm" },
    sourced: { glyph: "~", tip: "info.provSourced" },
    verified: { glyph: "✓", tip: "info.provVerified" },
    // A live Wikipedia read shares the green *and* the ✓ of `verified`: both are an
    // inspectable, non-LLM extract of a real source, so a newcomer reads one "this is
    // trustworthy" checkmark rather than a cryptic "W" (the tooltip still names which).
    wikipedia: { glyph: "✓", tip: "info.provWikipedia" },
  };
  // `extra` (optional) is the concrete source shown *first* in the tooltip (the
  // per-claim drug pill's verbatim quote + page ref, or a bibliographic citation),
  // followed after a blank line by the grade explainer (`base`): the actual source
  // is what the reader wants up top, the tier explanation is the footnote under it
  // (.help-tip is white-space:pre-line so the newlines show).
  const makeProvenancePill = (level, extra) => {
    const spec = PROVENANCE_PILLS[level];
    const base = spec ? t(spec.tip) : t("info.provNone");
    // `extra` is usually a string; it may be a Node (e.g. a clickable source link),
    // in which case keep it live and append the grade explainer under it (the
    // .help-tip is white-space:pre-line, so the blank line renders).
    let tip;
    if (extra instanceof Node) {
      tip = document.createDocumentFragment();
      tip.append(extra, document.createTextNode(`\n\n${base}`));
    } else {
      tip = extra ? `${extra}\n\n${base}` : base;
    }
    const cls = spec ? `src-pill src-prov-${level}` : "src-pill src-todo";
    const pill = el("button", cls, spec ? spec.glyph : NOSOURCE_GLYPH);
    pill.type = "button";
    pill.setAttribute("aria-label", base);
    return withTip(pill, tip);
  };

  // One tooltip line for a single source. Every source is quote-level
  // {corpus,page,quote,provenance} (the one shape used everywhere): it renders the
  // verbatim quote + "<ref>, p.N", resolving the ref from meta.sourceCorpora by
  // `corpus`. A corpus source with no page (e.g. a PDSP Ki reference) shows just the
  // ref line; a `quote` prefixes it.
  const sourceTipLine = (s) => {
    if (!s || !s.corpus) return "";
    const corpora = (data.meta && data.meta.sourceCorpora) || {};
    const c = corpora[s.corpus] || {};
    const label = c.ref || c.short || s.corpus;
    const ref = s.page != null
      ? t("info.sourceRef", { corpus: label, page: s.page })
      : label;
    const line = s.quote ? `“${s.quote}”\n— ${ref}` : `— ${ref}`;
    // An expression source (GtoPdb tissue distribution) names the assay species;
    // show it so a non-human claim is explicit on the pill itself, not only the tag.
    return s.species
      ? `${line}\n${t("info.sourceSpecies", { species: speciesLabel(s.species) })}`
      : line;
  };

  // Localized species name for an assay/expression source (Human/Rat/Mouse/Monkey,
  // as stored in the data); an unknown value passes through unchanged.
  const speciesLabel = (s) => {
    const key = { Human: "species.human", Rat: "species.rat",
      Mouse: "species.mouse", Monkey: "species.monkey" }[s];
    return key ? t(key) : (s || "");
  };

  // The tooltip tail under a per-claim provenance pill: every source (all
  // quote-level now) rendered as a line. Shared by the binding + NbN rows and the
  // pathway rows / connection panel, so a pathway's source shows on both endpoints'
  // panels.
  const sourcesTip = (sources) =>
    (sources || []).map(sourceTipLine).filter(Boolean).join("\n\n");

  // The corpus reference for a Ki source, rendered as the tooltip "extra": the corpus
  // label made a live link to the exact source (ki.reference pinned-revision permalink,
  // falling back to the corpus's generic URL) when a URL is available, else plain text
  // (the reference on its own line). Returned as a fragment so the link stays clickable.
  // Shared by kiChip's verified badge and the binding row's source pill, so a literature
  // Ki (e.g. a Wikipedia pharmacodynamics table) is reachable from both, not only the Ki
  // badge. `dash` prepends the leading source-line dash marker (the binding pill wants it;
  // kiChip does not, since it appends its own kiCited explainer after).
  const kiCorpusRefNode = (ki, { dash = false } = {}) => {
    const label = ki.corpusRef || "PDSP Ki Database";
    const refUrl = /^https?:\/\//i.test(ki.reference || "") ? ki.reference
      : (/^https?:\/\//i.test(ki.corpusUrl || "") ? ki.corpusUrl : "");
    const frag = document.createDocumentFragment();
    if (dash) frag.append("— ");
    if (refUrl) {
      const a = el("a", null, label);
      a.href = refUrl;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      frag.append(a);
    } else {
      frag.append(label + (ki.reference ? "\n" + ki.reference : ""));
    }
    return frag;
  };

  // The provenance pill for a drug binding row (shared by the drug panel's "Acts
  // on" list and a target panel's "Interacting drugs" list, the same resolved
  // binding object). Its grade + tooltip come from whatever backs the binding: its
  // own quote-level Stahl source if present, else its measured PDSP Ki (which lifts
  // it to verified, mirroring _binding_grade), else nothing -> a NOSOURCE pill.
  // There is no drug-level citation fallback: an unsourced binding honestly shows
  // NOSOURCE rather than borrowing the book at large. When the backing is a Ki whose
  // corpus is URL-addressable (a literature Ki, e.g. the Wikipedia table), the label
  // is a clickable link, matching the Ki badge's tooltip below the row.
  const bindingProvenancePill = (binding) => {
    if (binding.sources && binding.sources.length)
      return makeProvenancePill(binding.provenance, sourcesTip(binding.sources));
    if (binding.ki)
      return makeProvenancePill(binding.provenance,
        kiCorpusRefNode(binding.ki, { dash: true }));
    return makeProvenancePill(binding.provenance);
  };

  // The strongest-affinity binding a drug has feeding a transmitter system (the
  // binding whose flowKind == kind, min representative Ki), or undefined. The one
  // node behind the drug<->system link, so the drug panel's "Projections affected"
  // row and the projection-group panel's "Drugs acting on this system" row rank +
  // source it identically. (bindingKi, the shared Ki key, is module-scope above.)
  const strongestBindingForKind = (bindings, kind) =>
    bindings.filter((b) => b.flowKind === kind)
      .sort((a, b) => bindingKi(a) - bindingKi(b))[0];

  // Shared label / value row for the classification "facts" block (receptor,
  // target and drug views), optionally led by a coloured swatch so a row's colour
  // matches the dots + legend. Empty values are skipped.
  const addFactRow = (facts, label, value, color, opts = {}) => {
    const links = opts.links && opts.links.filter((lk) => lk && lk.text);
    // Render if there is a value, clickable links, or just a trailing pill (a
    // "Source: [pill]" row carries only the grade pill, no text value).
    if (!value && !(links && links.length) && !opts.pill) return;
    const r = el("div", "info-fact");
    r.appendChild(el("span", "fact-label", label));
    const v = el("span", "fact-value");
    if (color) {
      const sw = el("span", "swatch line");
      sw.style.background = color;
      v.appendChild(sw);
    }
    if (links && links.length) {
      // Clickable parts (a drug's Class / Nomenclature) that each run a search,
      // joined by ", " inside one inline wrapper so the commas flow naturally
      // (the row itself is a flex container).
      const wrap = el("span", "fact-links");
      links.forEach((lk, i) => {
        if (i) wrap.appendChild(document.createTextNode(", "));
        const btn = el("button", "fact-link", lk.text);
        btn.type = "button";
        btn.addEventListener("click", () => onSearchPick(lk.query));
        wrap.appendChild(btn);
      });
      v.appendChild(wrap);
    } else {
      v.appendChild(document.createTextNode(value));
    }
    // Optional trailing provenance pill (e.g. the NbN's quote source), so a
    // sourced fact carries the same grade pill as a binding row.
    if (opts.pill) v.appendChild(opts.pill);
    // Optional muted trailing note (e.g. flagging a non-standard nomenclature).
    if (opts.note) v.appendChild(el("span", "fact-note", opts.note));
    r.appendChild(v);
    facts.appendChild(r);
  };

  // A coloured effect glyph (+ boost / − block / ≈ modulate, in the effect's colour)
  // that replaces the plain colour bar at the head of a drug binding row, so the
  // action's direction reads at a glance. `label` (the localized effect name) is the
  // accessible name. When there is a label the glyph is wrapped in a tap-to-explain
  // tooltip (withTip): a tap on it shows the effect name and, crucially, stops the
  // tap from bubbling to the clickable binding row (so on a phone tapping the "+/−"
  // no longer navigates away, per the request); on desktop it also shows on hover.
  const effectGlyph = (effect, color, label) => {
    const g = el("span", "effect-glyph", EFFECT_GLYPHS[effect] || "·");
    g.style.color = color;
    if (label) g.setAttribute("aria-label", label);
    return label ? withTip(g, label) : g;
  };

  // Format a Ki (nM) to ~3 significant figures without trailing noise (0.29, 2.7,
  // 1240), so 0.28999999... reads as 0.29.
  const fmtKi = (n) => {
    const p = Number(n);
    return isFinite(p) ? String(parseFloat(p.toPrecision(3))) : "?";
  };

  // The measured PDSP Ki shown to the right of a binding's source badge: the median
  // value + [min-max] range + human/non-human assay counts, then its own "truth
  // badge" (a verified provenance pill whose tooltip cites the one representative
  // assay: species, preparation, radioligand, reference). A value borrowed through
  // the alias map (an enantiomer/prodrug/metabolite) also gets a visible ⚠ warning
  // naming the compound it was actually measured on, so it is never read as this
  // drug's own number. Returns a fragment appended to the binding row.
  const kiChip = (ki) => {
    const frag = document.createDocumentFragment();
    // A literature Ki (a quote-gated corpus like Wikipedia) is a single value quoted
    // from a source, not a raw assay: it has no ki_id and no human/non-human counts.
    // Render it plainly (value + optional range + a "literature value" tag), with the
    // corpus + revision permalink in the pill tooltip; skip the assay-only chrome
    // (species counts, "measured in non-human", the alias ⚠ warning).
    const measured = ki.kiId != null || ki.nHuman > 0 || ki.nNonhuman > 0;
    if (!measured) {
      const chip = el("span", "ki-chip");
      chip.appendChild(el("span", "ki-val", `Ki ${fmtKi(ki.median)} nM`));
      chip.appendChild(el("span", "ki-detail",
        (ki.min !== ki.max ? `${fmtKi(ki.min)}–${fmtKi(ki.max)} · ` : "")
        + t("drug.kiCited")));
      frag.appendChild(chip);
      // The corpus label doubles as the link to the exact source (see kiCorpusRefNode:
      // ki.reference's pinned-revision permalink, else the corpus URL), so a click opens
      // the very table the value was quoted from. The kiCited explainer follows;
      // makeProvenancePill then appends the grade explainer under it.
      const extra = kiCorpusRefNode(ki);
      extra.append("\n\n" + t("drug.kiCitedTip"));
      frag.appendChild(makeProvenancePill(ki.provenance, extra));
      return frag;
    }
    const chip = el("span", "ki-chip");
    chip.appendChild(el("span", "ki-val", `Ki ${fmtKi(ki.median)} nM`));
    chip.appendChild(el("span", "ki-detail",
      `${fmtKi(ki.min)}–${fmtKi(ki.max)} · `
      + t("drug.kiCounts", { h: ki.nHuman, n: ki.nNonhuman })
      + (ki.inactive ? " · " + t("drug.kiInactive", { n: ki.inactive }) : "")));
    if (ki.nHuman === 0) chip.classList.add("ki-nonhuman");
    frag.appendChild(chip);
    // Truth badge: the assay behind the value.
    const assay = [
      ki.kiId != null ? `#${ki.kiId}` : "",
      ki.valueNm != null ? `${fmtKi(ki.valueNm)} nM` : "",
      ki.species, ki.preparation, ki.radioligand, ki.reference,
    ].filter(Boolean).join(", ");
    let tip = t("drug.kiTip", { h: ki.nHuman, n: ki.nNonhuman,
      assay: `${ki.corpusRef}: ${assay}` });
    if (ki.nHuman === 0) {
      tip += "\n\n" + t("drug.kiTipNonHuman", { species: ki.species || "?" });
    }
    if (ki.inactive) {
      tip += "\n\n" + t("drug.kiInactiveTip", { n: ki.inactive });
    }
    const relationLabel = ki.mapped
      ? t(`drug.rel.${ki.relation}`) || ki.relation : "";
    if (ki.mapped) {
      tip += "\n\n" + t("drug.kiMappedTip",
        { compound: ki.measuredAs, relation: relationLabel });
    }
    frag.appendChild(makeProvenancePill(ki.provenance, tip));
    if (ki.mapped) {
      const warn = el("span", "ki-mapped",
        "⚠ " + t("drug.kiMapped", { compound: ki.measuredAs }));
      warn.title = t("drug.kiMappedTip",
        { compound: ki.measuredAs, relation: relationLabel });
      frag.appendChild(warn);
    }
    return frag;
  };

  // One binding row, shared by the drug panel's "Acts on" list and a
  // receptor/target panel's "Interacting drugs" list: the two render the *same*
  // resolved binding from opposite ends (a drug's target vs a target's drug), so
  // the markup lives once. Layout: the effect glyph, then a text column holding
  // the leading name, the action line, and (stacked under them) the measured Ki
  // chip with its own verified badge; the binding's source pill sits to the right
  // of that whole block. `nameText` leads the row (the target name on a drug
  // panel, the drug name on a target panel); `onActivate`, when given, makes the
  // row a clickable link. An affinity_only binding (PDSP Ki, no known direction)
  // gets a muted neutral glyph + an "affinity only" line and no source pill (Stahl
  // never stated it; the Ki's verified badge is its only source).
  const bindingRow = (binding, drug, nameText, onActivate) => {
    const li = el("li");
    const affinity = binding.affinityOnly;
    if (binding.tentative) li.classList.add("tentative");
    if (affinity) li.classList.add("affinity-only");
    li.appendChild(effectGlyph(
      binding.effect, affinity ? "#8a8f98" : binding.effectColor,
      affinity ? t("drug.affinityOnly") : binding.effectLabel));
    const txt = el("div", "bind-text");
    // Name + the binding's own source pill share the first line, so the pill sits
    // right of the target name rather than being stranded at the far panel edge
    // past the (wide) Ki line below it. An affinity_only binding carries no source
    // pill (its Ki's verified badge is the only source), so the name stands alone.
    const nameRow = el("div", "bind-name");
    nameRow.appendChild(el("span", "bind-target", nameText));
    if (!affinity) nameRow.appendChild(bindingProvenancePill(binding));
    txt.appendChild(nameRow);
    const parts = [affinity ? t("drug.affinityOnly") : binding.actionLabel,
                   binding.note];
    if (binding.tentative) parts.push(t("drug.speculative"));
    const detail = parts.filter(Boolean).join(" · ");
    if (detail) txt.appendChild(el("span", "bind-action", detail));
    // Ki stacked under the name+action, with its own verified badge beside it.
    if (binding.ki) {
      const kiLine = el("div", "bind-ki");
      kiLine.appendChild(kiChip(binding.ki));
      txt.appendChild(kiLine);
    }
    li.appendChild(txt);
    li.title = affinity
      ? `${t("drug.affinityOnly")} · ${nameText}`
      : `${binding.effectLabel} · ${nameText}`;
    if (onActivate) {
      li.classList.add("clickable");
      li.addEventListener("click", onActivate);
    }
    return li;
  };

  // Shared by the structure / receptor / drug / target views: an external reference
  // link, rendered only for an http(s) url so a stray field can never inject markup.
  // A present link carries no provenance pill: the description just above it already
  // shows a "sourced" grade for the same Wikipedia source, so a second pill grading
  // the link only repeated it. A missing reference still renders the label + the
  // red NOSOURCE pill, so the gap stays visible like a source.
  const appendWiki = (url) => {
    const ok = typeof url === "string" && /^https?:\/\//i.test(url);
    const wrap = el("div", "info-wiki");
    if (ok) {
      const a = el("a", null, t("info.wikipedia"));
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      wrap.appendChild(a);
    } else {
      wrap.appendChild(el("span", null, t("info.reference")));
      wrap.appendChild(makeProvenancePill(null)); // no reference -> NOSOURCE pill
    }
    body.appendChild(wrap);
    return wrap; // returned so it can anchor a live Wikipedia description below it
  };

  // Append an external "look this up" link (a search-by-name convenience that lands
  // on a results page, e.g. EMA / FDA / Drugs.com for a drug, PDSP for a receptor)
  // onto a reference row's wiki wrap, after a `·` separator. Not a source for any
  // specific claim, so it carries no provenance pill; only linked (navigated to),
  // never fetched, so the CSP is unaffected.
  const appendLookupLink = (wrap, labelKey, href, titleKey) => {
    wrap.appendChild(el("span", "ref-sep", "·"));
    const a = el("a", null, t(labelKey));
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.title = t(titleKey);
    wrap.appendChild(a);
    return a;
  };
  // The PDSP Ki database has no URL-addressable per-target search, so every
  // receptor/target links to the same browse page (a "go look it up" convenience).
  const PDSP_KIDB_URL = "https://pdspdb.unc.edu/kidb2/kidb/web/kis-results/index";
  // UniProt + Guide to Pharmacology (GtoPdb) name searches for a receptor: land on
  // each site's results page for the receptor's name. UniProt is filtered to human
  // (model_organism 9606). Convenience search links (navigated to, never fetched),
  // so no CSP change + no provenance pill.
  const uniprotSearchUrl = (name) =>
    `https://www.uniprot.org/uniprotkb?query=${encodeURIComponent(name)}&facets=model_organism%3A9606`;
  const gtopdbSearchUrl = (name) =>
    "https://www.guidetopharmacology.org/GRAC/DatabaseSearchForward?searchString="
    + encodeURIComponent(name)
    + "&searchCategories=all&species=none&type=all&comments=includeComments&order=rank";

  // Live Wikipedia description, shared by every panel carrying a `wikipedia` link
  // (drug / receptor / structure / target). Best-effort: it fetches the current
  // lead for the viewer's locale (js/wiki.js, English fallback) and shows it as one
  // or more "sourced" info-desc paragraphs. `paragraph` is a baked description <p>
  // to swap
  // in place (drug/receptor); when there is none a fresh <p> is inserted relative to
  // `anchor` (the wiki link wrap) only once the live text arrives, so a structure /
  // target with no baked description gains one only on success. `before` puts that
  // fresh paragraph *above* the anchor (so the live description reads above the link
  // it backs, matching the baked-description panels); default is below. A failed /
  // blocked / absent fetch is a no-op, so the panel is unchanged offline. When the
  // live lead arrives it always rewrites the paragraph (text + green Wikipedia pill),
  // replacing any baked fallback: a live fetch is a programmatic verbatim read of the
  // article, so it grades higher than the baked snapshot it supersedes.
  const liveWikiDescription = (url, {
    paragraph = null, anchor = null, before = false,
  } = {}) => {
    if (typeof url !== "string" || !/^https?:\/\//i.test(url)) return;
    fetchWikiLead(url, window.__I18N__.lang).then((live) => {
      if (!live || !live.text) return;
      let p = paragraph;
      if (p) {
        if (!p.isConnected) return; // panel re-rendered to something else
      } else {
        if (!anchor || !anchor.isConnected) return; // panel gone / replaced
        p = el("p", "info-desc");
        anchor[before ? "before" : "after"](p);
      }
      // The live lead is now the full intro (several newline-separated
      // paragraphs): the first reuses `p`, the rest become sibling <p>s, and the
      // provenance pill trails the last so it all reads as one sourced block.
      const paras = live.text.split(/\n+/).map((s) => s.trim()).filter(Boolean);
      p.textContent = paras.length ? paras[0] : live.text;
      let last = p;
      for (let i = 1; i < paras.length; i += 1) {
        const extra = el("p", "info-desc", paras[i]);
        last.after(extra);
        last = extra;
      }
      last.appendChild(document.createTextNode(" "));
      last.appendChild(makeProvenancePill("wikipedia"));
    });
  };

  // The canonical "intro" block shared by EVERY node panel (structure / receptor
  // / target / drug): the baked description paragraph (when the node has one) with
  // its provenance pill, then the Wikipedia reference link *below* the text it
  // backs, then the live-lead refresh. Centralizing it guarantees the same
  // element order and the same sourcing treatment on every panel, instead of each
  // show*() re-composing the two and drifting (which is how the link came to sit
  // above the description on some panels and below it on the drug one). `description`
  // is the baked text (omit for a structure/target, which carry none); a present
  // wiki link with no baked description still gains the live lead *above* it.
  const appendReference = ({
    url, description = "", descriptionProvenance = "",
    descriptionExtra = "",
  } = {}) => {
    let paragraph = null;
    if (description) {
      paragraph = el("p", "info-desc", description);
      if (descriptionProvenance) {
        paragraph.appendChild(document.createTextNode(" "));
        paragraph.appendChild(
          makeProvenancePill(descriptionProvenance, descriptionExtra));
      }
      body.appendChild(paragraph);
    }
    // Link goes after the description so the reference sits below the text it backs.
    const wiki = appendWiki(url);
    liveWikiDescription(url, paragraph
      ? { paragraph }
      : { anchor: wiki, before: true });
    return { paragraph, wiki };
  };

  // Wikipedia illustration block (hero + lazy "show more" gallery), shared by the
  // structure and circuit panels: both hot-link a Wikimedia hero (resolved by
  // tools/fetch_structure_images.py) plus an optional gallery of further gif/svg.
  // Multi-MB, so hot-linked not vendored (CSP img-src allows upload.wikimedia.org),
  // with a spinner while loading and a silent figure-removal on failure. Colour art,
  // so never inverted. `altName` names the subject for the alt text; the gallery is
  // built lazily on first expand so the extra images never load unless asked. No-op
  // when there is no hero, so a panel can call it unconditionally.
  const appendWikiImages = (heroUrl, gallery, altName) => {
    if (!heroUrl) return;
    const figure = (src) => {
      const fig = el("figure", "structure-image loading");
      fig.appendChild(el("div", "img-spinner"));
      const img = document.createElement("img");
      img.alt = t("structure.imageAlt", { name: altName });
      img.loading = "lazy";
      img.decoding = "async";
      img.title = t("image.zoomHint");
      img.dataset.optional = "1"; // self-handled failure: no global error banner
      img.addEventListener("load", () => fig.classList.remove("loading"));
      img.addEventListener("error", () => fig.remove());
      img.addEventListener("click", () =>
        onImagePick(img.currentSrc || img.src, img.alt, { invert: false }));
      img.src = src;
      fig.appendChild(img);
      return fig;
    };
    body.appendChild(figure(heroUrl));
    const gal = gallery || [];
    if (!gal.length) return;
    const wrap = el("div", "structure-gallery");
    wrap.hidden = true;
    const toggle = el("button", "btn gallery-toggle");
    toggle.type = "button";
    let built = false;
    const sync = () => {
      toggle.textContent = wrap.hidden
        ? t("structure.galleryShow", { n: gal.length })
        : t("structure.galleryHide");
    };
    toggle.addEventListener("click", () => {
      if (!built) {
        for (const url of gal) wrap.appendChild(figure(url));
        built = true;
      }
      wrap.hidden = !wrap.hidden;
      sync();
    });
    sync();
    body.appendChild(toggle);
    body.appendChild(wrap);
  };


  // Group a {drug, binding}[] by primary drug category and append the category
  // sub-headings + rows into `container`. Shared by the group/target's own
  // "Interacting drugs" list and the per-subtype dropdowns below it, so the sort +
  // row shape can never drift between the two. Sort: within a class, strongest-
  // affinity drug first (by this target's binding Ki, Infinity when unmeasured; equal
  // Ki tie-broken by name); classes ordered by the class's hardest binding (its min
  // Ki), classes with no measured Ki keeping the meta / Drugs-legend order among
  // themselves. Matches the drug panel's "Acts on" order and the target legend.
  const appendDrugsByCategory = (list, container) => {
    const cats = data.meta.drugCategoryLabels || {};
    const byCat = new Map();
    for (const item of list) {
      const cat = (item.drug.categories && item.drug.categories[0]) || "other";
      if (!byCat.has(cat)) byCat.set(cat, []);
      byCat.get(cat).push(item);
    }
    for (const items of byCat.values()) {
      items.sort((a, b) => {
        const ka = bindingKi(a.binding), kb = bindingKi(b.binding);
        return ka !== kb ? ka - kb : a.drug.name.localeCompare(b.drug.name);
      });
    }
    const metaOrder = [...Object.keys(cats),
                       ...[...byCat.keys()].filter((c) => !(c in cats))];
    const classKi = new Map();
    for (const [cat, its] of byCat)
      classKi.set(cat, Math.min(...its.map((it) => bindingKi(it.binding))));
    const order = [...byCat.keys()].sort((a, b) => {
      const ka = classKi.get(a), kb = classKi.get(b);
      return ka !== kb ? ka - kb : metaOrder.indexOf(a) - metaOrder.indexOf(b);
    });
    for (const cat of order) {
      container.appendChild(el("h4", "drug-cat", cats[cat] || cat));
      const ul = el("ul");
      // Same shared row builder as the drug panel's "Acts on" list (same resolved
      // binding, seen from the target's side), so the effect glyph, action, the
      // measured Ki chip and the shared source pill all render identically here;
      // clicking a row opens that drug.
      for (const { drug, binding } of byCat.get(cat)) {
        ul.appendChild(bindingRow(binding, drug, drug.name, () => onDrugPick(drug)));
      }
      container.appendChild(ul);
    }
  };

  // Shared by the receptor + target views: the drugs that act on this target, so
  // you can go from a target to every drug touching it (grouped by category, see
  // appendDrugsByCategory). Omitted entirely when no drug in the dataset acts on it.
  const appendInteractingDrugs = (targetId) => {
    const list = (data.drugsByTarget && data.drugsByTarget.get(targetId)) || [];
    if (!list.length) return;
    const wrap = el("div", "info-bindings info-interactors");
    wrap.appendChild(el(
      "h3", null, `${t("targets.interactingDrugs")} (${list.length})`));
    appendDrugsByCategory(list, wrap);
    body.appendChild(wrap);
  };

  // A receptor_group panel (α2 / glutamate) links to its modeled subtype receptors
  // (target.subtypes, a sourceless taxonomy). Below the group's own interacting
  // drugs, list each subtype that has drugs of its own in a collapsed <details>
  // dropdown, so from the coarse α2 panel you can reach (and expand) the drugs that
  // bind α2A/B/C/D specifically (e.g. asenapine at α2A). Subtypes with no interacting
  // drug are skipped; the whole section is omitted when none qualify.
  const appendSubtypeInteractors = (subtypes) => {
    if (!Array.isArray(subtypes) || !subtypes.length) return;
    const withDrugs = subtypes
      .map((sid) => ({
        sid, list: (data.drugsByTarget && data.drugsByTarget.get(sid)) || [],
      }))
      .filter((s) => s.list.length);
    if (!withDrugs.length) return;
    const wrap = el("div", "info-bindings info-interactors info-subtype-interactors");
    wrap.appendChild(el("h3", null, t("targets.bySubtype")));
    for (const { list } of withDrugs) {
      // The subtype's display name comes off the resolved binding (localized), so it
      // needs no separate receptor lookup and stays in sync with the drug panel.
      const name = (list[0].binding && list[0].binding.targetName) || "";
      const details = el("details", "subtype-group");
      details.appendChild(el("summary", null, `${name} (${list.length})`));
      appendDrugsByCategory(list, details);
      wrap.appendChild(details);
    }
    body.appendChild(wrap);
  };

  // One clickable <li> for a pathway that is a member of some grouping (a
  // A bold, colour-filled direction arrow (short shaft + a wide pointy head) for a
  // connection row: far more legible than the old thin colour bar + tiny glyph,
  // and it carries the pathway colour itself. `dir` is "out" (this structure
  // projects to the other endpoint), "in" (receives from it), or "both"
  // (reciprocal / commissural). Drawn as inline SVG so the head is genuinely wide
  // and it stays crisp at any size (a Unicode arrowhead's shape varies by font).
  const SVG_NS = "http://www.w3.org/2000/svg";
  const DIR_TIP = { out: "info.dirOut", in: "info.dirIn", both: "info.dirBoth" };
  // The localized "what this arrow's colour means" line for a pathway: the kind
  // label (the colour IS the projection kind, meta.projectionColors[kind]) plus the
  // neurotransmitter, matching the connection panel's type line. Empty for a pathway
  // with no kind. Shared so the arrow tooltip and that line can't drift.
  const colourMeaningOf = (proj) => {
    const kindLabel = (data.meta.kindLabels && data.meta.kindLabels[proj.kind])
      || proj.kind || "";
    return [kindLabel, proj.neurotransmitter].filter(Boolean).join(" · ");
  };
  const directionArrow = (color, dir, colourMeaning = "") => {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", "conn-arrow");
    svg.setAttribute("viewBox", "0 0 26 16");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d",
      dir === "in"
        ? "M24,6 L12,6 L12,2 L2,8 L12,14 L12,10 L24,10 Z"
        : dir === "both"
        ? "M2,8 L9,2 L9,6 L17,6 L17,2 L24,8 L17,14 L17,10 L9,10 L9,14 Z"
        : "M2,6 L14,6 L14,2 L24,8 L14,14 L14,10 L2,10 Z"); // "out" (default)
    path.setAttribute("fill", color || "#fff");
    svg.appendChild(path);
    // Tap-to-explain: a tap shows what the arrow means (its direction AND, when
    // known, its colour = the pathway kind), and stops the tap bubbling to the
    // clickable row it sits over, so on a phone tapping the arrow no longer navigates
    // into the pathway/region (per the request); hover shows it on desktop too.
    let tip = t(DIR_TIP[dir] || DIR_TIP.out);
    if (colourMeaning) tip += `\n${t("info.arrowColour", { label: colourMeaning })}`;
    return withTip(svg, tip);
  };

  // One pathway row, shared by every "connections" list (a structure's
  // connections, a circuit's loop, a projection group): the bold direction arrow
  // in the pathway colour, the label text, the pathway's summary source pill, and
  // a click that jumps to the connection via onConnectionPick. `dir` is passed by
  // the caller (showStructure rows are relative to the structure; circuit / group
  // rows show the full route, so they pass "both" for a reciprocal pathway else
  // "out", matching their "from -> to" label text).
  const pathwayRow = (proj, dir, labelText) => {
    const li = el("li");
    li.title = proj.label || "";
    li.appendChild(directionArrow(proj.color, dir, colourMeaningOf(proj)));
    li.appendChild(el("span", "conn-label", labelText));
    // Always show the grade pill; an unsourced pathway shows NOSOURCE, never a blank
    // (a node's provenance is never simply absent from the panel).
    li.appendChild(makeProvenancePill(proj.provenance, sourcesTip(proj.sources)));
    li.addEventListener("click", () => onConnectionPick(proj));
    return li;
  };

  // Build a <ul> of pathway rows with left/right twins collapsed. `rowOf(proj)`
  // returns `{dir, label}` (the direction glyph + the row text, both using
  // hemisphere-stripped base names): mirrored twins then share direction + label,
  // so keying on `dir|label|pathway` keeps the first and drops its L/R duplicate.
  // Shared by the structure panel and the circuit/group member lists so a midline
  // source (the raphe) that projects to both hemispheres lists each target once.
  // Returns the list element + the surviving row count (for the "(N)" heading).
  const pathwayList = (projs, rowOf) => {
    const seen = new Set();
    const ul = el("ul");
    let count = 0;
    for (const proj of projs) {
      const { dir, label } = rowOf(proj);
      const key = `${dir}|${label}|${proj.label || proj.kind}`;
      if (seen.has(key)) continue;
      seen.add(key);
      ul.appendChild(pathwayRow(proj, dir, label));
      count++;
    }
    return { ul, count };
  };

  // A titled "member pathways" list (the circuit + projection-group panels): one
  // pathwayRow per projection, each showing its full from -> to route (twins
  // collapsed via pathwayList).
  const appendPathwayList = (titleText, projs) => {
    if (!projs.length) return;
    const { ul, count } = pathwayList(projs, (proj) => {
      const glyph = proj.bidirectional ? "↔" : "→";
      return {
        dir: proj.bidirectional ? "both" : "out",
        label: `${baseNameOf(proj.from)} ${glyph} ${baseNameOf(proj.to)}`,
      };
    });
    const wrap = el("div", "info-connections");
    wrap.appendChild(el("h3", null, `${titleText} (${count})`));
    wrap.appendChild(ul);
    body.appendChild(wrap);
  };

  // A node's identity line: its "what is this" group heading carrying the node's own
  // source grade pill. Shared by the structure / circuit / group panels, which each
  // state one identity claim (a receptor/target/drug instead pills each fact row). The
  // grade rides this line, never a "Sources" block below the member lists (which would
  // read as grading the members). `always` shows a NOSOURCE pill even when ungraded,
  // for nodes whose badge is required (circuit / group are llm-only today); a structure
  // omits the pill when its anatomy grade is absent.
  const appendSourcedHeading = (labelText, provenance, sources, always = false) => {
    const groupEl = el("div", "info-group", labelText);
    if (always || provenance) {
      groupEl.appendChild(document.createTextNode(" "));
      groupEl.appendChild(makeProvenancePill(provenance || null, sourcesTip(sources)));
    }
    body.appendChild(groupEl);
  };

  return {
    show(proj) {
      body.innerHTML = "";
      body.appendChild(el("h2", "info-title", proj.label || t("info.connection")));
      // Type line: the connection's analogue of a structure's group line ("Lobe"
      // etc.), stating plainly what this node is (a projection / neuron pathway).
      body.appendChild(el("div", "info-group", t("info.projectionType")));

      // The pathway's one source grade (strongest over its citations), shown on
      // each data row below so every claim (route, transmitter, description) carries
      // its own badge, rather than a single block at the bottom that leaves it
      // unclear which node it backs. The tooltip lists the citation(s).
      const provPill = () =>
        makeProvenancePill(proj.provenance, sourcesTip(proj.sources));

      // Route line: from -> to (or <-> for a bidirectional/commissural link), each
      // endpoint clickable to jump to (and isolate) that structure.
      const route = el("div", "info-route");
      route.appendChild(endpointEl(proj.from));
      route.appendChild(el("span", "conn-dir", proj.bidirectional ? "↔" : "→"));
      route.appendChild(endpointEl(proj.to));
      route.appendChild(provPill());
      body.appendChild(route);

      // Kind swatch + kind/transmitter text + its source badge.
      const meta = el("div", "info-meta");
      const swatch = el("span", "swatch line");
      swatch.style.background = proj.color || "#fff";
      meta.appendChild(swatch);
      // Localized functional kind + transmitter, via the shared colourMeaningOf so
      // this type line and the arrow's colour-meaning tooltip can't drift.
      meta.appendChild(el("span", null, colourMeaningOf(proj)));
      meta.appendChild(provPill());
      body.appendChild(meta);

      // Short description + its source badge (inline at the end, like the receptor
      // baked-description pill).
      if (proj.description) {
        const p = el("p", "info-desc", proj.description);
        p.appendChild(document.createTextNode(" "));
        p.appendChild(provPill());
        body.appendChild(p);
      }
    },

    /**
     * Populate the panel for a *structure* (clicking a region, a double-click,
     * or a structure search result): its name, group, and the list of pathways
     * touching it. Each connection row is clickable and routes through
     * onConnectionPick so the caller can frame it + open the connection panel.
     */
    showStructure(structure) {
      body.innerHTML = "";
      body.appendChild(el("h2", "info-title", structure.name));
      // The anatomy classification grade (existence / group / position) rides the
      // group line it actually grades, not a broad "Source" row at the bottom (a
      // source always sits on the specific node it backs). Omitted when the anatomy
      // grade is absent (structures are the only node kind that may be ungraded).
      appendSourcedHeading(
        data.meta.groupLabels[structure.group] || structure.group,
        structure.classification_provenance, structure.sources);

      // Wikipedia illustration (the lead rotating-brain GIF, else an SVG diagram or
      // an infobox image) + its lazy "show more" gallery, via the shared helper (see
      // appendWikiImages): hot-linked, spinner while loading, silent hide on failure.
      appendWikiImages(structure.structureImage, structure.structureImageGallery,
        structure.name);

      // External reference (Wikipedia) + its live lead summary, via the shared
      // appendReference (structures carry no baked description, so the live lead,
      // when it arrives, appears above the link).
      appendReference({ url: structure.wikipedia });

      // Pathways with this structure at either end, in the data's order, with
      // left/right twins collapsed (via pathwayList): a midline source (e.g. the
      // raphe) projects to both hemispheres of each target, which would otherwise
      // list as two rows differing only by "Left"/"Right". Each row shows just the
      // other endpoint's hemisphere-stripped base name, direction relative to this
      // structure (out it projects, in it receives, both reciprocal/commissural).
      const conns = data.projections.filter(
        (p) => p.from === structure.id || p.to === structure.id);
      if (conns.length === 0) {
        body.appendChild(el("p", "info-desc", t("info.noConnections")));
        return;
      }

      const { ul, count } = pathwayList(conns, (proj) => {
        const outgoing = proj.from === structure.id;
        const otherId = outgoing ? proj.to : proj.from;
        return {
          dir: proj.bidirectional ? "both" : outgoing ? "out" : "in",
          label: baseNameOf(otherId),
        };
      });
      const wrap = el("div", "info-connections");
      wrap.appendChild(el(
        "h3", null, `${t("info.connections")} (${count})`));
      wrap.appendChild(ul);
      body.appendChild(wrap);
    },

    /**
     * Populate the panel for a *receptor* (clicking a receptor legend row): its
     * name, neurotransmitter system, a Wikipedia link, a one-line description, the
     * classification facts (neurotransmitter, mechanism type, excit/inhib/modulatory
     * effect with its sign swatch, pre/post-synaptic site) and where it is
     * expressed (the region list, "Throughout the brain" for a ubiquitous receptor,
     * or a no-CNS-role note for a stub). Built fresh each call like the others.
     */
    showReceptor(receptor) {
      body.innerHTML = "";
      body.appendChild(el("h2", "info-title", receptor.name));
      body.appendChild(el("div", "info-group", receptor.familyLabel));

      const { wiki: recWiki } = appendReference({
        url: receptor.wikipedia, description: receptor.description,
      });
      // External lookups beside the reference: PDSP Ki (binding affinity; a browse
      // link, PDSP has no per-target search URL), UniProt (human-only) and the Guide
      // to Pharmacology (GtoPdb), both name-searched on the receptor's name.
      appendLookupLink(recWiki, "info.pdsp", PDSP_KIDB_URL, "info.pdspTitle");
      appendLookupLink(recWiki, "info.uniprot", uniprotSearchUrl(receptor.name), "info.uniprotTitle");
      appendLookupLink(recWiki, "info.gtopdb", gtopdbSearchUrl(receptor.name), "info.gtopdbTitle");

      // Classification facts as label / value rows; the "effect" value carries the
      // sign swatch so the colour matches the dots + legend row. Each attribute
      // (family / class / sign / synaptic) is its OWN graded sub-claim, so each row
      // shows its OWN pill from receptor.classification[attr]: a quote that only
      // backs the sign no longer lends a verified badge to the GPCR or pre/post
      // claim it never addressed. Unsourced attributes read honestly as llm.
      const attrPill = (attr) => {
        const entry = (receptor.classification || {})[attr] || {};
        return makeProvenancePill(
          entry.grade,
          entry.sources && entry.sources.length
            ? sourcesTip(entry.sources) : undefined);
      };
      const facts = el("div", "info-facts");
      addFactRow(facts, t("receptor.neurotransmitter"), receptor.neurotransmitter,
        null, { pill: attrPill("family") });
      addFactRow(facts, t("receptor.type"), receptor.classLabel,
        null, { pill: attrPill("receptor_class") });
      addFactRow(facts, t("receptor.effect"), receptor.signLabel, receptor.signColor,
        { pill: attrPill("sign") });
      addFactRow(facts, t("receptor.synaptic"), receptor.synapticLabel,
        null, { pill: attrPill("synaptic") });
      body.appendChild(facts);

      // Where it is expressed.
      const where = el("div", "info-locations");
      where.appendChild(el("h3", null, t("receptor.foundIn")));
      if (receptor.ubiquitous) {
        const p = el("p", "info-desc info-desc-pilled", t("receptor.ubiquitous"));
        const u = receptor.ubiquitousInfo;
        if (u) {
          const tip = u.sources && u.sources.length
            ? sourcesTip(u.sources) : t("receptor.locUnsourced");
          p.appendChild(makeProvenancePill(u.provenance, tip));
        }
        where.appendChild(p);
      } else if (receptor.locationNames.length === 0) {
        where.appendChild(el("p", "info-desc", t("receptor.noRole")));
      } else {
        where.appendChild(locationList(receptor.locationNames, receptor.locations,
          receptor.locationInfo));
      }
      body.appendChild(where);

      // Drugs that act on this receptor, grouped by category.
      appendInteractingDrugs(receptor.id);
    },

    /**
     * Populate the panel for a non-receptor *target* (a transporter / enzyme / ion
     * channel / receptor group, clicked in the merged "Receptors & targets" section
     * or a target search result): its name, its neurotransmitter system (or
     * "Other"), a Wikipedia link (or a TODO pill until one is gathered), the type +
     * system facts, and the regions it sits in. Receptors keep the richer
     * showReceptor view; this is the lighter sibling for the non-receptor targets.
     */
    showTarget(target) {
      body.innerHTML = "";
      body.appendChild(el("h2", "info-title", target.name));
      body.appendChild(el(
        "div", "info-group", target.systemLabel || t("targets.otherSystem")));

      // Reference + live lead (targets carry no baked description), via the shared
      // appendReference, so the link sits under any live lead like every panel.
      const { wiki: tgtWiki } = appendReference({ url: target.wikipedia });
      // PDSP covers transporters / enzymes / ion channels too, so the same lookup.
      appendLookupLink(tgtWiki, "info.pdsp", PDSP_KIDB_URL, "info.pdspTitle");

      // The classification grade (type / system claims) sits on each fact's OWN row
      // rather than a single broad "Source" row below, so a source always grades the
      // specific node beside it. A fresh pill per row; only when the row has a value
      // (so an empty System row still drops instead of showing a bare pill).
      const tgtPill = () => makeProvenancePill(
        target.classificationProvenance,
        target.sources && target.sources.length
          ? sourcesTip(target.sources) : undefined);
      const withPill = (v) => (v && target.classificationProvenance ? { pill: tgtPill() } : {});
      const facts = el("div", "info-facts");
      addFactRow(facts, t("receptor.type"), target.typeLabel, target.swatchColor,
        withPill(target.typeLabel));
      addFactRow(facts, t("receptor.system"), target.systemLabel, null,
        withPill(target.systemLabel));
      // Tone-polarity row: its OWN sourced sub-claim, NOT the classification grade.
      // The vesicular/sign flags flip the drug-flow overlay's direction, so a wrong
      // one silently inverts a drug's apparent effect on tone; surfacing it with its
      // own pill keeps that claim honestly graded (e.g. α2's autoreceptor character
      // reads llm until quote-verified, VMAT2's vesicular claim reads verified).
      if (target.polarityProvenance) {
        const polText = target.vesicular
          ? t("target.polarityVesicular")
          : (target.polaritySign === "inhibitory"
            ? t("target.polarityAutoreceptor") : null);
        if (polText) {
          const polPill = makeProvenancePill(
            target.polarityProvenance,
            target.polaritySources && target.polaritySources.length
              ? sourcesTip(target.polaritySources) : undefined);
          addFactRow(facts, t("target.polarity"), polText, null, { pill: polPill });
        }
      }
      if (facts.childElementCount) body.appendChild(facts);

      // Where it sits (same "Found in" list as a receptor; empty -> no footprint).
      const where = el("div", "info-locations");
      where.appendChild(el("h3", null, t("receptor.foundIn")));
      if (!target.locationNames.length) {
        where.appendChild(el("p", "info-desc", t("receptor.noRole")));
      } else {
        where.appendChild(locationList(target.locationNames, target.locationBases,
          target.locationInfo));
      }
      body.appendChild(where);

      // Drugs that act on this target, grouped by category.
      appendInteractingDrugs(target.id);
      // For a receptor_group (α2 / glutamate): drugs binding each modeled subtype
      // (α2A/B/C/D, ...) in a collapsed per-subtype dropdown below the group's own.
      appendSubtypeInteractors(target.subtypes);
    },

    /**
     * Populate the panel for a *drug* (clicking a drug legend/list row or a drug
     * search result): its name, primary category, a Wikipedia link, a one-line
     * description, its class(es) + nomenclature, then the "Acts on" list of
     * molecular targets (each binding's effect swatch + target name + action,
     * with a note / "speculative" marker when present, and a source pill: its own
     * quote-level source or the drug-level Stahl citation as a fallback).
     */
    showDrug(drug) {
      body.innerHTML = "";
      body.appendChild(el("h2", "info-title", drug.name));
      if (drug.category) body.appendChild(el("div", "info-group", drug.category));

      // Combination drug: no PDSP Ki of its own (it is a mixture). Warn, and link to
      // each constituent we model as a standalone drug so its binding profile is one
      // click away; interactions between the constituents may exist.
      if (drug.combo && drug.combo.length) {
        const warn = el("div", "combo-warning");
        warn.appendChild(el("strong", null, t("drug.combo")));
        warn.appendChild(el("p", null, t("drug.comboNote")));
        const links = el("div", "combo-parts");
        drug.combo.forEach((c, i) => {
          if (i) links.appendChild(document.createTextNode(" · "));
          const linked = c.drugId && drugById.get(c.drugId);
          if (linked && linked.focusable) {
            const a = el("button", "combo-link", c.name);
            a.type = "button";
            a.addEventListener("click", () => onDrugPick(linked));
            links.appendChild(a);
          } else {
            links.appendChild(el("span", "combo-plain", c.name));
          }
        });
        warn.appendChild(links);
        body.appendChild(warn);
      }

      // Vendored molecular-structure SVG (from Wikipedia, see tools/fetch_molecules.py).
      // It is black/grey line art on transparent; the .mol-structure CSS inverts it
      // to read as light strokes on the dark panel. Absent when no SVG was fetched.
      if (drug.structureImage) {
        const fig = el("figure", "mol-structure");
        const img = document.createElement("img");
        img.alt = t("drug.structureAlt", { name: drug.name });
        img.decoding = "async";
        img.title = t("image.zoomHint");
        // A failed molecule SVG degrades gracefully (drop the figure, no broken
        // icon) and opts out of the global error banner, exactly like the Wikipedia
        // illustrations: an absent diagram is not an app error to shout about.
        img.dataset.optional = "1";
        img.addEventListener("error", () => fig.remove());
        // Click to enlarge; the lightbox inverts it too so the line-art reads on
        // the dark backdrop, matching the panel's .mol-structure treatment.
        img.addEventListener("click", () =>
          onImagePick(img.currentSrc || img.src, img.alt, { invert: true }));
        img.src = drug.structureImage; // set src last, after error handler is wired
        fig.appendChild(img);
        body.appendChild(fig);
      }

      // Description (the drug's Wikipedia lead, baked + live-refreshed) then the
      // Wikipedia link below it, via the shared appendReference. A "sourced"
      // description is the WP lead (CC BY-SA); an "llm" one a mechanism synthesis.
      const { wiki } = appendReference({
        url: drug.wikipedia, description: drug.description,
        descriptionProvenance: drug.descriptionProvenance,
        descriptionExtra: drug.descriptionProvenance === "sourced"
          ? t("info.descFromWikipedia") : "",
      });
      // External drug-database lookup links beside the reference. Each is a
      // search-by-name link (it always lands on a results page), a convenience
      // lookup rather than a source for a specific claim, so none carries a
      // provenance pill; all are only linked (navigated to), never fetched, so the
      // CSP is unaffected. Vidal (the French database) shows only in French; the
      // EMA (Europe) and the US FDA show regardless of locale. ANSM is intentionally
      // absent: its ecodex search has no URL-addressable form to deep-link.
      if (wiki) {
        const addLookup = (labelKey, href, titleKey) =>
          appendLookupLink(wiki, labelKey, href, titleKey);
        const q = encodeURIComponent(drug.name);
        // Drugs.com search by name. A search link (always lands on the drug),
        // chosen over a direct /monograph/<name>.html so it never 404s for a drug
        // whose monograph slug differs (combos especially); shown regardless of
        // locale.
        addLookup(
          "info.drugscom",
          "https://www.drugs.com/search.php?searchterm="
            + encodeURIComponent(drug.name.toLowerCase()),
          "info.drugscomTitle");
        if (window.__I18N__.lang === "fr") {
          addLookup(
            "info.vidal",
            "https://www.vidal.fr/recherche/substances.html?query="
              + encodeURIComponent(drug.name.toLowerCase()),
            "info.vidalTitle");
        }
        addLookup(
          "info.ema",
          "https://www.ema.europa.eu/en/search?search_api_fulltext=" + q,
          "info.emaTitle");
        addLookup(
          "info.fda",
          "https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm"
            + "?event=BasicSearch.process&searchTerm=" + q,
          "info.fdaTitle");
      }

      // Classification facts: the coarse class(es) and the NbN nomenclature line.
      // Both are clickable: each runs a search (class:"..." / nbn:"...") that filters
      // to the matching drugs, so you can pivot from one drug to its whole class. The
      // class list shows one clickable chip per category.
      const facts = el("div", "info-facts");
      // The class classification is its own node: pill it (its own grade, or the
      // verbatim quote when category_sources exist), so the claim "this drug is an
      // SSRI/..." carries its provenance beside the value like every other node.
      const catPill = drug.categorySources && drug.categorySources.length
        ? makeProvenancePill(drug.categoryProvenance, sourcesTip(drug.categorySources))
        : makeProvenancePill(drug.categoryProvenance || null);
      addFactRow(facts, t("drug.class"), null, null, {
        links: drug.categoryLabels.map((label) => ({
          text: label,
          query: `class:"${label}"`,
        })),
        pill: catPill,
      });
      if (drug.nbn) {
        // The NbN line is quote-sourced from Stahl; show its provenance pill
        // (with the verbatim quote in the tooltip) beside the clickable value. If a
        // drug ever carries an NbN value with no source, still show a pill (its
        // grade, else the red NOSOURCE pill) so the node is never left unbadged.
        const nbnPill = drug.nbnSources && drug.nbnSources.length
          ? makeProvenancePill(drug.nbnProvenance, sourcesTip(drug.nbnSources))
          : makeProvenancePill(drug.nbnProvenance || null);
        addFactRow(facts, t("drug.nomenclature"), null, null, {
          links: [{ text: drug.nbn, query: `nbn:"${drug.nbn}"` }],
          pill: nbnPill,
          // A newer drug with no formal NbN carries Stahl's drug-class descriptor
          // instead; flag it so the value isn't misread as an official NbN.
          note: drug.nbnNonstandard ? t("drug.nbnNonstandard") : null,
        });
      }
      if (facts.childElementCount) body.appendChild(facts);

      // (Ki ranking uses the shared bindingKi helper.)

      // What it binds: one row per target, coloured by the action's net effect.
      const acts = el("div", "info-bindings");
      acts.appendChild(el("h3", null, t("drug.actsOn")));
      if (!drug.bindings.length) {
        acts.appendChild(el("p", "info-desc", t("drug.noTargets")));
      } else {
        const ul = el("ul");
        // Strongest-affinity first: order by the binding's representative Ki
        // ascending, so the target a drug grips hardest tops the list; bindings with
        // no measured Ki sink to the bottom. Sort a copy (leave the authored array
        // untouched); a stable sort keeps the authored order within each tier.
        const bindings = [...drug.bindings].sort((a, b) => bindingKi(a) - bindingKi(b));
        for (const b of bindings) {
          // If this binding's target is browsable on its own (in the merged
          // "Receptors & targets" list and focusable), make the row jump to it.
          const tgt = targetById.get(b.target);
          const onActivate = tgt && tgt.focusable
            ? () => onTargetPick(tgt) : null;
          ul.appendChild(bindingRow(b, drug, b.targetName, onActivate));
        }
        acts.appendChild(ul);
      }
      body.appendChild(acts);
      // No standalone drug-level "Source(s)" block: the Stahl citation that backs
      // the drug is shown per-binding (each binding's pill above), so a source
      // always refers to a specific binding node rather than "the whole drug".

      // Projections affected: the ascending pathway systems this drug's flow overlay
      // lights (drug.flowKinds, from meta.system_flow_kinds). A *derived* inference
      // from the drug's *tone-setter* bindings only (a reuptake/enzyme/vesicle target
      // or a presynaptic autoreceptor, see js/data.js flowSystems): the net signed
      // tone gives each row a direction (an out-arrow = raises the system's tone, an
      // in-arrow = lowers it) and the affinity its intensity. Each row jumps to that
      // projection group and carries the source of the strongest-affinity binding on
      // the system (the same source that says "X is an agonist"), so the inference
      // stays traceable. Only shows for the four modeled ascending systems; a purely
      // postsynaptic drug sets no tone -> empty flowKinds -> section omitted.
      const groupsByKey = data.projectionGroupsByKey;
      const projColors = data.meta.projectionColors || {};
      if ((drug.flowKinds || []).length && groupsByKey) {
        const proj = el("div", "info-connections");
        proj.appendChild(el("h3", null, t("drug.projectionsAffected")));
        proj.appendChild(el("p", "legend-caption", t("drug.projectionsAffectedHint")));
        const ul = el("ul");
        for (const kind of drug.flowKinds) {
          const group = groupsByKey.get(`kind:${kind}`);
          if (!group) continue;
          // Representative = the strongest-affinity binding feeding this system, so
          // the row's source is the most concrete claim behind the inference.
          const rep = strongestBindingForKind(drug.bindings, kind);
          // Net signed tone (js/data.js flowSystems): out-arrow raises the system's
          // tone, in-arrow lowers it (an autoreceptor agonist, a VMAT2 blocker).
          const flow = (drug.flowSystems || {})[kind];
          const li = el("li", "clickable");
          li.title = group.name;
          li.appendChild(directionArrow(projColors[kind] || "#fff",
            flow && flow.direction < 0 ? "in" : "out",
            (data.meta.kindLabels && data.meta.kindLabels[kind]) || kind));
          li.appendChild(el("span", "conn-label", group.name));
          if (rep) li.appendChild(bindingProvenancePill(rep));
          li.addEventListener("click", () => onProjectionGroupPick(group));
          ul.appendChild(li);
        }
        proj.appendChild(ul);
        body.appendChild(proj);
      }
    },

    /**
     * Populate the panel for a *circuit* (clicking a Circuits legend row / search):
     * its name (with the loop's source grade on the heading line), a sourced
     * description, the structures it loops through (deduped to bases, each clickable
     * to jump to that region) and its member pathways (the projections with both
     * endpoints in the loop, derived not stored). Mirrors the structure panel's
     * shape; the member-pathway + region rows reuse the shared pathwayRow /
     * locationList so nothing is duplicated.
     */
    showCircuit(circuit) {
      body.innerHTML = "";
      body.appendChild(el("h2", "info-title", circuit.name));
      // The circuit's source grade sits on its identity line (always shown, NOSOURCE
      // when llm-only), not a "Sources" block below the member lists (which would read
      // as grading the members, not the circuit).
      appendSourcedHeading(
        t("circuit.heading"), circuit.provenance, circuit.sources, true);

      // Wikipedia illustration (hero + lazy gallery), the same hot-linked treatment a
      // brain structure gets (see appendWikiImages); no-op when unillustrated.
      appendWikiImages(circuit.structureImage, circuit.structureImageGallery,
        circuit.name);

      // Description (baked fallback) + the Wikipedia reference below it, then the
      // live-lead refresh (upgrades to the current WP lead when reachable), via the
      // same shared appendReference every panel uses. Like a brain structure, the
      // circuit reads its text from Wikipedia; the baked copy is the offline
      // fallback and carries the loop's own citation grade until the live lead lands.
      appendReference({
        url: circuit.wikipedia, description: circuit.description,
        descriptionProvenance: circuit.provenance,
      });

      // Structures in the loop, deduped to bases (so the two hemispheres collapse
      // to one row), each rendered as a link that jumps to the region via
      // onStructurePick (locationList wires the click; the `.info-locations` class
      // gives it the clickable link styling). No per-structure source pill: a
      // structure's membership in the loop is not a separate sourced claim, it is
      // part of the circuit node itself, which is already graded on the heading
      // above (`circuit.provenance`). Each linked structure carries its own anatomy
      // grade on its own panel.
      const seen = new Set();
      const names = [];
      const bases = [];
      for (const id of circuit.structures) {
        const base = id.replace(/_[RL]$/, "");
        if (seen.has(base)) continue;
        seen.add(base);
        const s = data.byId.get(id);
        names.push(s ? s.base_name : base);
        bases.push(base);
      }
      if (bases.length) {
        const where = el("div", "info-locations");
        where.appendChild(el("h3", null, t("circuit.structures")));
        where.appendChild(locationList(names, bases));
        body.appendChild(where);
      }

      // Member pathways: every projection with both endpoints inside the loop (the
      // same rule the viewer uses to light a circuit's arrows), so the panel never
      // duplicates the circuit -> arrows mapping.
      const idSet = new Set(circuit.structures);
      const members = data.projections.filter(
        (p) => idSet.has(p.from) && idSet.has(p.to));
      appendPathwayList(t("circuit.pathways"), members);
    },

    /**
     * Populate the panel for a *projection group* (clicking a Projections legend
     * row, in either colour mode): its name, a heading saying whether it groups by
     * transmitter or by sign (carrying the group's source grade), a sourced
     * description (baked + live-refreshed from Wikipedia) with the reference link,
     * then its member pathways (the projections whose kind / sign matches the group,
     * derived not stored).
     */
    showProjectionGroup(group) {
      body.innerHTML = "";
      body.appendChild(el("h2", "info-title", group.name));
      // The group's source grade rides its identity line (always shown, NOSOURCE when
      // llm-only), not a "Sources" block at the bottom. The description keeps its own
      // grade below.
      appendSourcedHeading(
        group.mode === "sign" ? t("group.signHeading") : t("group.kindHeading"),
        group.provenance, group.sources, true);

      // Description (LLM-authored) + the Wikipedia reference below it, then the live
      // lead refresh (upgrades the paragraph to the current WP lead when reachable),
      // via the same shared appendReference every panel uses.
      appendReference({
        url: group.wikipedia, description: group.description,
        descriptionProvenance: group.classification_provenance,
      });

      // Member pathways: the projections this group stands for. In "kind" mode that
      // is every projection of the kind; in "sign" mode every projection folding to
      // the sign. Same derivation the legend uses to colour the arrows, so the panel
      // list always matches what is lit on screen.
      const members = data.projections.filter((p) =>
        group.mode === "sign" ? p.sign === group.key : p.kind === group.key);
      appendPathwayList(t("group.pathways"), members);

      // Drugs acting on this system: the mirror of the drug panel's "Projections
      // affected". Every focusable drug whose flow overlay lights this group (its
      // flowKinds includes this kind, i.e. it binds a receptor in the transmitter
      // system these pathways carry), so you can go from a pathway system to the
      // drugs that engage it. Non-directional, like the drug side. Only meaningful in
      // "kind" mode (a sign group has no transmitter system to map).
      if (group.mode === "kind") {
        const acting = (data.drugs || [])
          .filter((d) => d.focusable && (d.flowKinds || []).includes(group.key))
          .sort((a, b) => a.name.localeCompare(b.name));
        if (acting.length) {
          const wrap = el("div", "info-bindings info-interactors");
          wrap.appendChild(el(
            "h3", null, `${t("group.actingDrugs")} (${acting.length})`));
          const ul = el("ul");
          for (const d of acting) {
            const li = el("li", "clickable");
            li.title = d.name;
            li.appendChild(el("span", "bind-target", d.name));
            const cat = d.categoryLabels && d.categoryLabels[0];
            if (cat) li.appendChild(el("span", "legend-tag", cat));
            // Symmetric sourcing with the drug panel's "Projections affected" row:
            // the drug<->system link is one node, so both ends carry the same source,
            // the strongest-affinity binding feeding this system.
            const rep = strongestBindingForKind(d.bindings, group.key);
            if (rep) li.appendChild(bindingProvenancePill(rep));
            li.addEventListener("click", () => onDrugPick(d));
            ul.appendChild(li);
          }
          wrap.appendChild(ul);
          body.appendChild(wrap);
        }
      }
    },

    /** Register the handler run when a structure-panel connection row is clicked. */
    onConnection(fn) {
      onConnectionPick = fn;
    },

    /** Register the handler run when a drug-panel binding (target) row is clicked. */
    onTarget(fn) {
      onTargetPick = fn;
    },

    /**
     * Register the handler run when a region row in a receptor / target panel's
     * "Found in" list is clicked. Called with the structure base id; the caller
     * resolves it to a mesh and jumps to that structure.
     */
    onStructure(fn) {
      onStructurePick = fn;
    },

    /**
     * Register the handler run when a drug row in a receptor / target panel's
     * "Interacting drugs" list is clicked. Called with the drug record; the caller
     * focuses it exactly like its Drugs legend row / search pick.
     */
    onDrug(fn) {
      onDrugPick = fn;
    },

    /**
     * Register the handler run when a projection-group row in a drug panel's
     * "Projections affected" list is clicked. Called with the group record; the
     * caller focuses it exactly like its Projections legend row / search pick.
     */
    onProjectionGroup(fn) {
      onProjectionGroupPick = fn;
    },

    /**
     * Register the handler run when a clickable Class / Nomenclature value in a drug
     * panel is clicked. Called with a `field:"value"` search query string; the caller
     * opens the search box pre-filled with it.
     */
    onSearch(fn) {
      onSearchPick = fn;
    },
    /** Set the handler that enlarges a clicked panel image (the lightbox). */
    onImage(fn) {
      onImagePick = fn;
    },
  };
}

/**
 * Build the merged "Receptors & targets" legend section from the live dataset
 * (#receptors-body): the unified `data.targets` list (every modeled receptor plus
 * every non-receptor drug target: transporters, enzymes, channels, receptor
 * groups), grouped by neurotransmitter `system`, so a transporter like SERT sits
 * under "Serotonergic" beside the 5-HT receptors. System headings are ordered by
 * **total knowledge nodes** (biggest first: the sum over the system's targets of
 * each target's own node + its "Found in" regions + the drug bindings on it, so a
 * heavily-expressed, heavily-drugged system like dopaminergic leads), with the
 * system-less "Other" bucket pinned last; members within a system are ordered
 * **lexicographically** by name. Each row is coloured by its swatch (a receptor's
 * sign colour, a target's type colour) and, for a non-receptor target, tagged with
 * its type ("transporter", ...). A focusable row is clickable (dim the brain to the
 * regions it sits in + scatter glowing dots, handled by the caller's `onPick`); a
 * footprint-less one (a receptor stub, an unlocated enzyme) renders muted + inert.
 * Returns a `reflect(activeId)` callback that lights the active row and greys the rest.
 * @param {import("./data.js").BrainData} data
 * @param {(target: object) => void} onPick
 * @returns {(activeId: string|null) => void}
 */
function buildTargetLegend(data, onPick) {
  const container = document.getElementById("receptors-body");
  if (!container) return () => {};
  container.replaceChildren();
  const rows = []; // { row, id } for the focusable entries

  const families = data.meta.receptorFamilyLabels || {};
  const drugsByTarget = data.drugsByTarget || new Map();

  // Group by system; a null system goes under the "_other" bucket.
  const bySystem = new Map();
  for (const tgt of data.targets || []) {
    const key = tgt.system || "_other";
    if (!bySystem.has(key)) bySystem.set(key, []);
    bySystem.get(key).push(tgt);
  }
  // Members within a system: plain lexicographic (natural) order by name, so the
  // list reads predictably (5-HT1A, 5-HT2A, ..., D1, D2, ...). `numeric` keeps
  // 5-HT2 before 5-HT10; `base` sensitivity folds case + accents.
  for (const [, list] of bySystem) {
    list.sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }));
  }
  // Each target's "size" is its knowledge nodes: the target itself, its expression
  // "Found in" regions (a ubiquitous receptor is one "throughout the brain" node),
  // and the drug bindings acting on it (data.drugsByTarget, deduped one per drug).
  const nodeCount = (tgt) => {
    const locs = tgt.receptor
      ? (tgt.receptor.ubiquitous ? 1 : tgt.receptor.locations.length)
      : (tgt.locationBases || []).length;
    const drugs = (drugsByTarget.get(tgt.id) || []).length;
    return 1 + locs + drugs;
  };
  // A system's node count is the sum over its targets, so a heavily-expressed,
  // heavily-drugged system (dopaminergic) outweighs a sparse one (melatoninergic).
  const groupNodes = new Map();
  for (const [key, list] of bySystem) {
    groupNodes.set(key, list.reduce((sum, tgt) => sum + nodeCount(tgt), 0));
  }
  // Heading order: most nodes first (the biggest systems lead), with the "_other"
  // system-less bucket pinned last regardless of its count.
  const order = [...bySystem.keys()].filter((k) => k !== "_other");
  order.sort((a, b) => groupNodes.get(b) - groupNodes.get(a));
  if (bySystem.has("_other")) order.push("_other");
  const done = new Set();
  for (const key of order) {
    if (done.has(key)) continue;
    done.add(key);
    const list = bySystem.get(key);
    if (!list || !list.length) continue;
    const h = document.createElement("h2");
    h.textContent = key === "_other" ? t("targets.otherSystem") : (families[key] || key);
    container.appendChild(h);
    for (const tgt of list) {
      const row = addLegendItem(container, tgt.swatchColor, tgt.name);
      // Non-receptor targets carry a muted kind tag ("transporter", "enzyme", ...)
      // so the merged list still reads at a glance (receptors need none).
      if (tgt.kind !== "receptor" && tgt.typeLabel) {
        const tag = document.createElement("span");
        tag.className = "legend-tag";
        tag.textContent = tgt.typeLabel;
        row.appendChild(tag);
      }
      if (tgt.focusable) {
        // Tooltip: a receptor's full classification, or a target's type · system.
        const r = tgt.receptor;
        row.title = r
          ? [r.neurotransmitter, r.classLabel, r.signLabel, r.synapticLabel]
              .filter(Boolean).join(" · ")
          : [tgt.typeLabel, tgt.systemLabel].filter(Boolean).join(" · ");
        row.classList.add("clickable");
        row.addEventListener("click", () => onPick(tgt));
        rows.push({ row, id: tgt.id });
      } else {
        // No modeled footprint (a receptor stub, an unlocated enzyme): listed for
        // completeness but not focusable.
        row.classList.add("muted");
        row.title = t("receptor.stubHint");
      }
    }
  }

  return function reflect(activeId) {
    for (const { row, id } of rows) {
      const selected = id === activeId;
      row.classList.toggle("selected", selected);
      row.classList.toggle("dimmed", activeId !== null && !selected);
    }
  };
}

/**
 * The drug's representative swatch colour: the net effect (boost/block/modulate)
 * most of its bindings share, so an SSRI reads green-ish and an antagonist-heavy
 * antipsychotic rose-ish at a glance. Falls back to a neutral grey.
 * @param {object} drug
 * @param {Object<string,string>} effectColors
 * @returns {string} hex colour
 */
function drugSwatchColor(drug, effectColors) {
  const counts = {};
  for (const b of drug.bindings || []) counts[b.effect] = (counts[b.effect] || 0) + 1;
  let best = null, bestN = -1;
  for (const [e, n] of Object.entries(counts)) if (n > bestN) { best = e; bestN = n; }
  return (best && effectColors[best]) || "#9aa0a6";
}

/**
 * Build the Drugs legend section (#drugs-list) from the live dataset, grouped by
 * coarse category (in the meta category-label order, drugs sorted A->Z within
 * each). Each row is coloured by the drug's dominant net effect and clickable to
 * focus it (dim the brain to the regions it acts on + animate its targets, via
 * the caller's `onPick`); a drug with no recorded bindings renders muted + inert.
 * The #drugs-filter box narrows the visible rows live (matching name + class +
 * targets), hiding emptied category headings and showing a "no match" note.
 * Returns a `reflect(activeId)` callback that lights the active drug's row.
 * @param {import("./data.js").BrainData} data
 * @param {(drug: object) => void} onPick
 * @returns {(activeId: string|null) => void}
 */
function buildDrugLegend(data, onPick) {
  const container = document.getElementById("drugs-list");
  const filterInput = document.getElementById("drugs-filter");
  if (!container) return () => {};
  container.replaceChildren();
  const rows = [];   // { row, id } for the focusable drugs (for reflect)
  const groups = []; // { heading, rows:[row,...] } for the live filter
  const effectColors = data.meta.drugEffectColors || {};
  const cats = data.meta.drugCategoryLabels || {};

  // Group drugs by their primary (first) category.
  const byCat = new Map();
  for (const drug of data.drugs || []) {
    const cat = (drug.categories && drug.categories[0]) || "other";
    if (!byCat.has(cat)) byCat.set(cat, []);
    byCat.get(cat).push(drug);
  }
  // Category order = the meta order first, then any leftover keys.
  const order = [...Object.keys(cats),
                 ...[...byCat.keys()].filter((c) => !(c in cats))];
  const done = new Set();
  for (const cat of order) {
    if (done.has(cat)) continue;
    done.add(cat);
    const list = byCat.get(cat);
    if (!list || !list.length) continue;
    list.sort((a, b) => a.name.localeCompare(b.name));
    const h = document.createElement("h2");
    h.textContent = cats[cat] || cat;
    container.appendChild(h);
    const groupRows = [];
    for (const drug of list) {
      const row = addLegendItem(
        container, drugSwatchColor(drug, effectColors), drug.name, true);
      row.classList.add("drug-item");
      row._haystack = foldText(`${drug.name} ${drug.keywords}`);
      if (drug.focusable) {
        row.classList.add("clickable");
        row.title = drug.categoryLabels.join(" · ");
        row.addEventListener("click", () => onPick(drug));
        rows.push({ row, id: drug.id });
      } else {
        row.classList.add("muted");
        row.title = t("drug.stubHint");
      }
      groupRows.push(row);
    }
    groups.push({ heading: h, rows: groupRows });
  }

  // "No match" note for the filter (hidden unless every row is filtered out).
  const empty = document.createElement("p");
  empty.className = "drugs-empty info-desc";
  empty.textContent = t("drugs.none");
  empty.hidden = true;
  container.appendChild(empty);

  const applyFilter = () => {
    const q = foldText((filterInput?.value || "").trim());
    let anyVisible = false;
    for (const g of groups) {
      let groupVisible = false;
      for (const row of g.rows) {
        const match = !q || row._haystack.includes(q);
        row.hidden = !match;
        if (match) groupVisible = true;
      }
      g.heading.hidden = !groupVisible;
      if (groupVisible) anyVisible = true;
    }
    empty.hidden = anyVisible;
  };
  if (filterInput) {
    filterInput.value = "";
    filterInput.addEventListener("input", applyFilter);
  }

  return function reflect(activeId) {
    for (const { row, id } of rows) {
      const selected = id === activeId;
      row.classList.toggle("selected", selected);
      row.classList.toggle("dimmed", activeId !== null && !selected);
    }
  };
}

// Camera directions for `?view=` (unit vectors from the framed target back to
// the camera). World axes: x right, y up, z toward the viewer / anterior.
const VIEW_DIRS = {
  front: [0, 0, 1],
  back: [0, 0, -1],
  right: [1, 0, 0],
  left: [-1, 0, 0],
  top: [0, 1, 0],
  bottom: [0, -1, 0],
  iso: [1, 0.55, 1.2],
};

/**
 * Point the camera so the currently visible meshes fill the frame, from a named
 * direction. Used by the screenshot URL params (`?view=`, `?only=`) so a single
 * structure can be inspected from a canonical angle. No-op if nothing visible.
 * @param {{camera:THREE.PerspectiveCamera, controls:OrbitControls, meshes:THREE.Mesh[]}} bundle
 * @param {string} viewName  Key of VIEW_DIRS (defaults to "iso").
 */
function frameVisible({ camera, controls, meshes }, viewName, onlyIds = null) {
  // `onlyIds` (a comma-joined id string) restricts the framing box to those
  // meshes, used by the solo review view so the camera frames the studied
  // structure while its ghosted neighbours stay in shot as context.
  const keep = onlyIds ? new Set(onlyIds.split(",").map((s) => s.trim()).filter(Boolean)) : null;
  const box = new THREE.Box3();
  let any = false;
  for (const mesh of meshes) {
    if (mesh.visible && (!keep || keep.has(mesh.userData.id))) {
      box.expandByObject(mesh);
      any = true;
    }
  }
  if (!any) return;

  const center = box.getCenter(new THREE.Vector3());
  const radius = box.getBoundingSphere(new THREE.Sphere()).radius;
  const dir = new THREE.Vector3(...(VIEW_DIRS[viewName] || VIEW_DIRS.iso)).normalize();
  // Distance that fits the bounding sphere in the vertical FOV, plus margin.
  const dist = (radius / Math.sin(THREE.MathUtils.degToRad(camera.fov) / 2)) * 1.3;

  camera.position.copy(center).addScaledVector(dir, dist);
  camera.near = Math.max(0.01, dist - radius * 2);
  camera.far = dist + radius * 4;
  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.update();
}

/**
 * Smooth camera framing shared by double-click, the reset button and search.
 *
 * Tweens both the orbit pivot (`controls.target`) and the camera position so a
 * structure (or the whole brain) ends up centered and reasonably sized. The
 * current viewing direction (target -> camera) is preserved so only the pivot
 * and distance change, which is far less disorienting than also swinging the
 * angle. The tween is advanced one step per frame by `tick()` and is cancelled
 * the instant the user grabs the controls (so a drag always wins).
 * @param {{camera:THREE.PerspectiveCamera, controls:OrbitControls, meshes:THREE.Mesh[]}} bundle
 */
function createCameraFocus({ camera, controls, meshes, getFocusMeshes }) {
  const sphere = new THREE.Sphere();
  const box = new THREE.Box3();
  const tmpVec = new THREE.Vector3();
  // The in-progress tween, or null when idle.
  let anim = null;
  // The structure last centered via focusStructure (double-click / structure
  // search), or null. Kept so the explode slider can re-aim the camera at it as
  // it moves; cleared whenever we frame something else (a connection or the
  // whole brain) so we don't chase a structure the user has navigated away from.
  let focused = null;
  // Pivot-follow: while anything is focused, dragging the Separate slider keeps the
  // focused thing centered by easing the orbit pivot onto its (moving) center, and
  // recenters smoothly when the view didn't start on it. Enabled by reaimFocused()
  // (called from the explode handler), advanced in tick(), and turned off once it
  // settles (so an idle focus costs nothing per frame), when the user grabs the
  // camera (cancel), or when the focus clears.
  let trackPivot = false;
  const PIVOT_EASE = 0.3;        // per-frame approach fraction while off-center
  const PIVOT_SNAP_FRAC = 0.05;  // within this * brain radius, snap (exact tracking)
  // The explode amount last applied, so zoomForExplode() only ever applies the
  // *incremental* distance change and thus preserves whatever zoom the user has
  // dialed in. The layout scales linearly with this (applyExplode pushes each
  // region to base * (1 + amount * EXPLODE_STRENGTH)).
  let lastExplode = 0;
  const spreadScale = (a) => 1 + a * EXPLODE_STRENGTH;
  // A structure's own (fixed) radius in world units: its geometry bounding sphere
  // scaled by the mesh scale. Cached on first use (geometry never changes).
  const meshReach = (mesh) => {
    const g = mesh.geometry;
    if (!g.boundingSphere) g.computeBoundingSphere();
    const s = Math.max(mesh.scale.x, mesh.scale.y, mesh.scale.z);
    return g.boundingSphere.radius * s;
  };
  // The whole assembly's outer radius from the brain centre at a given explode
  // amount: the farthest structure surface = max over regions of
  // (|base| * spreadScale(amount)) + that region's own radius. zoomForExplode
  // scales the camera distance by the *ratio* of this (not spreadScale alone),
  // which keeps the WHOLE brain a constant apparent size as it spreads. Matching
  // spreadScale alone over-pulls the camera back (it ignores the fixed structure
  // radii), so the brain visibly shrinks while exploding; matching the true outer
  // radius holds the brain steady, so only the individual structures look like
  // they shrink apart, which is the intent.
  const boundingRadiusAt = (amount) => {
    const k = spreadScale(amount);
    let maxR = 0;
    for (const mesh of meshes) {
      const r = mesh.userData.base.length() * k + meshReach(mesh);
      if (r > maxR) maxR = r;
    }
    return maxR || 1;
  };
  // Render-time screen offset (fractions of the viewport: +x slides the rendered
  // brain right, +y up), eased toward `offsetTarget` each tick and baked into the
  // camera as a view offset. It is a projection shift, not a move of the orbit
  // target, so it survives rotation / zoom / framing and reverts cleanly. Used to
  // slide the brain out from under the expanded panel on a phone (see
  // setScreenOffset wiring in wireControls).
  const offset = { x: 0, y: 0 };
  const offsetTarget = { x: 0, y: 0 };
  const OFFSET_EPS = 0.0005;
  // Bake the current offset into the camera's view offset (or clear it). Reads
  // the live viewport size every call so a resize self-heals without extra
  // bookkeeping.
  const applyOffset = () => {
    if (Math.abs(offset.x) < OFFSET_EPS && Math.abs(offset.y) < OFFSET_EPS) {
      if (camera.view && camera.view.enabled) camera.clearViewOffset();
      return;
    }
    const w = window.innerWidth;
    const h = window.innerHeight;
    // offsetX < 0 slides content right; offsetY > 0 slides content up (see the
    // updateProjectionMatrix math in three's PerspectiveCamera).
    camera.setViewOffset(w, h, -offset.x * w, offset.y * h, w, h);
  };

  // Distance at which a bounding sphere of `radius` fits the vertical FOV,
  // padded by `margin` (a bigger margin leaves more context around the target).
  const fitDistance = (radius, margin) =>
    (radius / Math.sin(THREE.MathUtils.degToRad(camera.fov) / 2)) * margin;

  // Begin a tween that looks at `center` and frames a sphere of `radius`,
  // keeping the present view direction.
  function tweenTo(center, radius, margin) {
    const dir = camera.position.clone().sub(controls.target);
    if (dir.lengthSq() < 1e-6) dir.set(...VIEW_DIRS.iso);
    dir.normalize();
    const dist = Math.max(controls.minDistance, fitDistance(radius, margin));
    anim = {
      fromTarget: controls.target.clone(),
      toTarget: center.clone(),
      fromPos: camera.position.clone(),
      toPos: center.clone().addScaledVector(dir, dist),
      start: performance.now(),
      duration: 500,
    };
  }

  // The live center of whatever is currently focused (the dimmed-in set the viewer
  // reports via getFocusMeshes), written into `out`; returns false when nothing is
  // focused. Prefers the explicitly focused single structure while it is still part
  // of that set, so a searched / double-clicked structure tracks precisely;
  // otherwise the whole set's bounding-sphere center, so a receptor / drug / circuit
  // focus (spanning many regions) stays framed as it explodes. Only visible meshes
  // count, so it composes with "See inside".
  function focusCenter(out) {
    const sel = getFocusMeshes && getFocusMeshes();
    if (!sel || !sel.length) return false;
    if (focused && focused.visible && sel.indexOf(focused) !== -1) {
      focused.getWorldPosition(out);
      return true;
    }
    box.makeEmpty();
    let any = false;
    for (const m of sel) if (m && m.visible) { box.expandByObject(m); any = true; }
    if (!any) return false;
    box.getBoundingSphere(sphere);
    out.copy(sphere.center);
    return true;
  }

  return {
    /** Center on and frame a single structure mesh (double-click / search). */
    focusStructure(mesh) {
      box.setFromObject(mesh).getBoundingSphere(sphere);
      // A generous margin keeps the structure centered but in context, rather
      // than filling the frame (which would just clip into its neighbors).
      tweenTo(sphere.center, sphere.radius, 2.2);
      // Remember it so reaimFocused() can keep it centered as it explodes out.
      focused = mesh;
    },
    /**
     * Frame a connection by fitting both of its endpoint structures, so picking
     * a pathway in the search recenters on the two regions it links.
     * @param {import("./arrows.js").ProjectionArrow} arrow
     */
    focusConnection(arrow) {
      box.makeEmpty();
      box.expandByObject(arrow.fromMesh);
      box.expandByObject(arrow.toMesh);
      box.getBoundingSphere(sphere);
      tweenTo(sphere.center, sphere.radius, 1.8);
      // A connection isn't a single structure to track, so stop following one.
      focused = null;
    },
    /**
     * Frame an arbitrary set of structure meshes by fitting their combined
     * bounding sphere, used when a receptor is picked in search (it spans several
     * regions). Ignores hidden meshes; a no-op if none are visible. Doesn't track
     * a single structure (the set isn't one), so it clears `focused` like
     * focusConnection.
     * @param {THREE.Mesh[]} meshList
     */
    focusMeshes(meshList) {
      box.makeEmpty();
      let any = false;
      for (const m of meshList) {
        if (m && m.visible) { box.expandByObject(m); any = true; }
      }
      if (!any) return;
      box.getBoundingSphere(sphere);
      tweenTo(sphere.center, sphere.radius, 1.8);
      focused = null;
    },
    /** Recenter the pivot on the middle of the brain and frame the whole thing. */
    recenter() {
      box.makeEmpty();
      for (const mesh of meshes) if (mesh.visible) box.expandByObject(mesh);
      if (box.isEmpty()) return;
      box.getBoundingSphere(sphere);
      tweenTo(sphere.center, sphere.radius, 1.4);
      focused = null;
    },
    /**
     * Instantly frame the whole visible brain (no tween), preserving the current
     * view direction. Used to seat the initial resting pose so a fresh load already
     * sits exactly where the reset button (recenter, same 1.4 margin) would put it,
     * instead of a hardcoded camera distance that only roughly matched.
     */
    frameAllNow() {
      box.makeEmpty();
      for (const mesh of meshes) if (mesh.visible) box.expandByObject(mesh);
      if (box.isEmpty()) return;
      box.getBoundingSphere(sphere);
      const dir = camera.position.clone().sub(controls.target);
      if (dir.lengthSq() < 1e-6) dir.set(...VIEW_DIRS.iso);
      dir.normalize();
      const dist = Math.max(controls.minDistance, fitDistance(sphere.radius, 1.4));
      controls.target.copy(sphere.center);
      camera.position.copy(sphere.center).addScaledVector(dir, dist);
      controls.update();
      focused = null;
    },
    /**
     * Called from the explode handler as the brain spreads: keep whatever is
     * focused (a single structure, or the multi-region set of a receptor / drug /
     * circuit / group focus) centered as it moves radially outward. It enables the
     * pivot-follow; tick() does the actual easing (gliding the orbit pivot in when
     * the view didn't start on the focus, then snapping to track the moving center
     * exactly). Only the pivot (controls.target) moves, so the camera rotates in
     * place, preserving the distance + angle the user set. A running framing tween
     * has its destination updated too so the two don't fight. Disabled when nothing
     * is focused.
     */
    reaimFocused() {
      trackPivot = focusCenter(tmpVec);
      if (trackPivot && anim) anim.toTarget.copy(tmpVec);
    },
    /**
     * Pull the camera back (or in) as the brain spreads, so the whole brain keeps
     * a *constant apparent size* (and the individual structures appear to shrink
     * as they separate) instead of overflowing or visibly shrinking. We scale the
     * camera->target distance by the ratio of the assembly's true outer radius
     * (boundingRadiusAt, which folds in the fixed structure radii) at the new vs
     * the last amount, so only the incremental change is applied and any manual
     * zoom the user has dialed in is preserved. OrbitControls' min/maxDistance
     * clamp the result on the next update. Call from the explode handler with the
     * slider's value.
     */
    zoomForExplode(amount) {
      const ratio = boundingRadiusAt(amount) / boundingRadiusAt(lastExplode);
      lastExplode = amount;
      if (Math.abs(ratio - 1) < 1e-6) return;
      tmpVec.copy(camera.position).sub(controls.target).multiplyScalar(ratio);
      camera.position.copy(controls.target).add(tmpVec);
    },
    /**
     * The factor by which the explode auto-zoom (zoomForExplode) has currently
     * pulled the camera back, relative to the assembled (amount 0) framing. So
     * `currentDistance / explodeZoom()` recovers the distance the user's own zoom
     * implies, with the spread's auto-pull divided out. The constant-width arrow
     * controller uses this so a spread (which auto-zooms) does not change arrow
     * width, only a genuine user zoom does.
     */
    explodeZoom() {
      return boundingRadiusAt(lastExplode) / boundingRadiusAt(0);
    },
    /**
     * Set the desired render-time screen offset (fractions of the viewport:
     * +x slides the brain right, +y up). Eased in/out by tick(). Pass 0,0 to
     * recenter. Survives rotation / zoom / framing (it's a projection shift).
     */
    setScreenOffset(x, y) {
      offsetTarget.x = x;
      offsetTarget.y = y;
    },
    /** Abort any running tween (used when the user starts interacting). */
    cancel() {
      anim = null;
      trackPivot = false; // a manual camera grab wins over the pivot-follow
    },
    /** Advance the active tween; call once per frame before controls.update().
     *  Returns true while a framing tween or the screen-offset ease is moving, so
     *  the on-demand render loop keeps drawing until both settle. */
    tick() {
      let active = false;
      if (anim) {
        const t = Math.min(1, (performance.now() - anim.start) / anim.duration);
        const e = t * t * (3 - 2 * t); // smoothstep ease in/out
        controls.target.lerpVectors(anim.fromTarget, anim.toTarget, e);
        camera.position.lerpVectors(anim.fromPos, anim.toPos, e);
        if (t >= 1) anim = null;
        active = true;
      } else if (trackPivot) {
        // No framing tween running: ease the orbit pivot toward the focused center.
        // Glide in when the view didn't start centered on it, then snap once close
        // so a slow spread tracks the (moving) center exactly with no lag. Turns
        // itself off once settled so an idle focus costs nothing per frame.
        if (focusCenter(tmpVec)) {
          const d = tmpVec.sub(controls.target); // tmpVec now = center - target
          const dist = d.length();
          if (dist > boundingRadiusAt(lastExplode) * PIVOT_SNAP_FRAC) {
            controls.target.addScaledVector(d, PIVOT_EASE);
            active = true;
          } else if (dist > 1e-4) {
            controls.target.add(d); // close enough: snap onto the center
            active = true;
          } else {
            trackPivot = false; // settled: stop following until the next spread
          }
        } else {
          trackPivot = false; // focus cleared
        }
      }
      // Ease the screen offset toward its target and (re)apply it. Runs every
      // frame independent of the framing tween, so the panel pan animates on its
      // own and a resize keeps the offset correctly scaled.
      if (
        Math.abs(offset.x - offsetTarget.x) > OFFSET_EPS ||
        Math.abs(offset.y - offsetTarget.y) > OFFSET_EPS
      ) {
        offset.x += (offsetTarget.x - offset.x) * 0.18;
        offset.y += (offsetTarget.y - offset.y) * 0.18;
        active = true;
      } else if (offset.x !== offsetTarget.x || offset.y !== offsetTarget.y) {
        offset.x = offsetTarget.x;
        offset.y = offsetTarget.y;
        active = true; // one last frame to apply the snap to target
      }
      applyOffset();
      return active;
    },
  };
}

/**
 * Apply screenshot/deep-link view parameters from the URL query string so the
 * headless renderer (tools/shot.py) can capture a specific view without any
 * interaction. Supported keys:
 *   explode, transparency : numbers (also move the sliders so the UI matches)
 *   autorotate            : truthy -> spin
 *   names=all             : force every structure label on
 *   only=id[,id2,...]     : show only these structures (others + all arrows hidden)
 *   view=front|back|left|right|top|bottom|iso : frame the visible meshes
 * Called after wireControls so the initial slider-driven layout is in place.
 * @param {object} bundle  { scene, camera, controls, meshes, arrows, labels }
 */
function applyViewParams(bundle) {
  const q = new URLSearchParams(window.location.search);
  if ([...q].length === 0) return;
  const { camera, controls, meshes, arrows } = bundle;

  const explode = document.getElementById("explode");
  const transparency = document.getElementById("transparency");
  const autorotate = document.getElementById("autorotate");

  if (q.has("explode")) {
    explode.value = q.get("explode");
    explode.dispatchEvent(new Event("input"));
  }
  if (q.has("transparency")) {
    transparency.value = q.get("transparency");
    transparency.dispatchEvent(new Event("input"));
  }
  // Auto-rotate is on by default for a live visit, but a deep link / screenshot
  // wants its exact framed view to hold still, so set it explicitly here (off
  // unless the param asks for it) instead of letting the default keep spinning.
  autorotate.checked = q.has("autorotate") && q.get("autorotate") !== "0";
  autorotate.dispatchEvent(new Event("change"));
  if (q.get("names") === "all") {
    document.getElementById("toggle-names").click();
  }
  // ?ui=0 hides the control panel (which now nests the toolbar, legend and the
  // detail/info pane) for clean, uncluttered shots (e.g. reviewing a shape).
  if (q.get("ui") === "0") {
    const el = document.getElementById("controls");
    if (el) el.style.display = "none";
  }

  if (q.has("only")) {
    const keep = new Set(q.get("only").split(",").map((s) => s.trim()).filter(Boolean));
    for (const mesh of meshes) mesh.visible = keep.has(mesh.userData.id);
    // Arrows are about relationships, not form; hide them all in isolated views.
    for (const arrow of arrows) arrow.setVisible(false);
    // Drop labels of now-hidden meshes (in case names=all was already applied).
    bundle.labels.refresh();
  }

  // `solo=id[,id2]`: the in-context shape-review view. Keep the whole brain
  // visible but render only the solo set solidly while the rest is ghosted to a
  // faint translucency (override the amount with `ghost=0..1`), so a structure's
  // fit against its neighbours can be judged. Used by tools/sculpt_shot.py; the
  // framing below targets the solo set. Arrows hidden (form, not relationships).
  if (q.has("solo")) {
    const solo = new Set(q.get("solo").split(",").map((s) => s.trim()).filter(Boolean));
    const ghost = q.has("ghost") ? Number(q.get("ghost")) : 0.06;
    for (const mesh of meshes) {
      const isSolo = solo.has(mesh.userData.id);
      mesh.material.transparent = !isSolo;
      mesh.material.opacity = isSolo ? 1 : ghost;
      mesh.material.depthWrite = isSolo;
    }
    for (const arrow of arrows) arrow.setVisible(false);
    bundle.labels.refresh();
  }

  // Frame whenever a view angle is requested, or a subset is isolated. With a
  // solo set, frame on it (the rest is only ghosted context, not framed).
  if (q.has("view") || q.has("only") || q.has("solo")) {
    frameVisible(bundle, q.get("view") || "iso", q.has("solo") ? q.get("solo") : null);
  }
}

/**
 * Fill the About panel's "Sources & provenance" block from meta.provenanceStats:
 * the grade key (reusing the .src-pill swatches the info panel shows beside each
 * source) and the programmatic coverage tally. The numbers come straight from the
 * data (generate_data.py _provenance_stats), so the headline % is a real count.
 */
function buildAboutSourcing(meta) {
  const host = document.getElementById("about-sourcing");
  if (!host) return;
  host.replaceChildren();

  const h = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  };

  // The "Sources & provenance" title is the #sourcing-modal's own <h2>; this block
  // is the intro + grade key + coverage tally. The intro + grade key need no loaded
  // data, so render them always: the popup is meaningful the instant it opens over
  // the loading overlay (the startup gate), called first with no meta, then again
  // with data.meta once loaded to fill the tally.
  host.appendChild(h("p", "about-text", t("about.sourcingIntro")));
  // A source is not proof: sources err, quote-to-claim mapping can slip, and the
  // viewer has bugs. Keep this prominent so nobody reads a pill as "true".
  host.appendChild(h("p", "about-caveat", t("about.sourcingCaveat")));

  // Grade key: a pill swatch + its meaning, in weakest-to-strongest order
  // (NOSOURCE first, then LLM-only up to verified). The pills reuse the
  // info-panel CSS classes so the legend matches the pills shown next to each source.
  const key = h("ul", "src-key");
  const keyRows = [
    ["src-todo", NOSOURCE_GLYPH, "about.gradeNone"],
    ["src-prov-llm", "?", "about.gradeLlm"],
    ["src-prov-sourced", "~", "about.gradeSourced"],
    ["src-prov-verified", "✓", "about.gradeVerified"],
  ];
  for (const [cls, glyph, tip] of keyRows) {
    const li = document.createElement("li");
    li.appendChild(h("span", `src-pill ${cls}`, glyph));
    li.appendChild(h("span", null, t(tip)));
    key.appendChild(li);
  }

  // Coverage tally: needs the loaded dataset's provenance stats, so it is skipped
  // on the first (pre-load, meta=null) call and filled in on the second. The grade
  // key reads better *after* the bars it explains, so append it last (below the
  // tally when there is one, otherwise it is all we have to show).
  const stats = meta && meta.provenanceStats;
  if (!stats) { host.appendChild(key); return; }

  // A headline over the knowledge nodes, then a per-node-kind bar.
  const a = stats.nodes || {};
  const wrap = h("div", "src-stats");
  wrap.appendChild(h("p", "src-stat-headline",
    t("about.sourcingHeadline", { pct: a.pct_backed, total: a.total })));
  const KIND_LABELS = {
    drug_bindings: "about.kindBindings",
    drug_nbn: "about.kindNbn",
    drug_categories: "about.kindDrugCategories",
    projections: "about.kindProjections",
    circuits: "about.kindCircuits",
    projection_groups: "about.kindProjectionGroups",
    receptors: "about.kindReceptors",
    receptor_class: "about.kindReceptorClass",
    receptor_sign: "about.kindReceptorSign",
    receptor_synaptic: "about.kindReceptorSynaptic",
    receptor_locations: "about.kindReceptorLocations",
    targets: "about.kindTargets",
    target_polarity: "about.kindTargetPolarity",
    target_locations: "about.kindTargetLocations",
    structures: "about.kindStructures",
    // Wikipedia `references` are deliberately NOT a coverage bar: a reference is a
    // pointer *at* a knowledge node, not itself a node, and every present link
    // defaults to `sourced` (so the bar was uniformly yellow and read as noise). It
    // stays in meta.provenance_stats.by_kind (data), just not rendered here.
  };
  // Rows are sorted best-coverage-first (highest % of backed nodes), ties broken by
  // the larger node count, so the strongest-sourced kinds head the list.
  const rows = [];
  for (const [kind, labelKey] of Object.entries(KIND_LABELS)) {
    const c = (stats.by_kind || {})[kind];
    if (!c || !c.total) continue;
    const verified = c.verified || 0;
    const sourced = c.sourced || 0;
    // Older meta lacked the llm/nosource split; fall back to lumping them as llm
    // (grey) so an out-of-date dataset still renders a sensible bar.
    const nosource = c.nosource != null ? c.nosource : 0;
    const llm = c.llm != null ? c.llm : (c.missing || 0) - nosource;
    const backed = verified + sourced;
    const pct = Math.round((100 * backed) / c.total);
    rows.push({ labelKey, verified, sourced, llm, nosource, backed, total: c.total, pct });
  }
  rows.sort((x, y) => y.pct - x.pct || y.total - x.total);
  // The four grade segments, strongest to weakest: (count, CSS class, tooltip label).
  const SEGMENTS = [
    ["verified", "src-seg-verified", "about.segVerified"],
    ["sourced", "src-seg-sourced", "about.segSourced"],
    ["llm", "src-seg-llm", "about.segLlm"],
    ["nosource", "src-seg-nosource", "about.segNone"],
  ];
  for (const r of rows) {
    const row = h("div", "src-stat-row");
    row.appendChild(h("span", "src-stat-label", t(r.labelKey)));
    row.appendChild(h("span", "src-stat-count", `${r.backed} / ${r.total} (${r.pct}%)`));
    const bar = h("div", "src-stat-bar");
    // One flush segment per non-empty grade, width proportional to its share, so a
    // partly-sourced kind reads as green+yellow+grey+red instead of green-on-empty.
    for (const [field, cls, labelKey] of SEGMENTS) {
      const n = r[field];
      if (!n) continue;
      const seg = h("span", cls);
      seg.style.width = `${(100 * n) / r.total}%`;
      bar.appendChild(seg);
    }
    // Per-grade counts tooltip via the shared attachTip (not a native `title`) so it
    // also works on touch: one tap pins it, a tap elsewhere dismisses it. zIndex 90
    // lifts the bubble above the #sourcing-modal (80) it lives in.
    attachTip(bar, SEGMENTS
      .map(([field, , labelKey]) => `${t(labelKey)}: ${r[field]}`)
      .join("  ·  "), { zIndex: 90 });
    row.appendChild(bar);
    wrap.appendChild(row);
  }
  // Measured-affinity (PDSP Ki) coverage: a SEPARATE honesty line, not a grade bar. A
  // binding backed by a Stahl quote with no Ki is still sourced, so this does not feed
  // the % above; it surfaces how much of the corpus carries a *measured* affinity and
  // how many drugs never had one looked up, so a fully quote-only corpus can't read as
  // exhaustively measured.
  const ki = stats.ki_coverage;
  if (ki && ki.bindings_total) {
    wrap.appendChild(h("p", "src-stat-kifoot", t("about.kiCoverage", {
      pct: ki.pct_bindings_with_ki,
      total: ki.bindings_total,
      drugsNone: ki.drugs_without_ki,
      drugs: ki.drugs_total,
    })));
  }
  host.appendChild(wrap);
  host.appendChild(key);
}

/** Wire the DOM controls to the scene behaviors. */
function wireControls({ controls, meshes, arrows, labels, focus, selection, projVis, cull }) {
  const autorotate = document.getElementById("autorotate");
  const seeInside = document.getElementById("see-inside");
  const toggleAnimations = document.getElementById("toggle-animations");
  const explode = document.getElementById("explode");
  const transparency = document.getElementById("transparency");
  const toggleNames = document.getElementById("toggle-names");
  const toggleProjections = document.getElementById("toggle-projections");
  const controlsToggle = document.getElementById("controls-toggle");
  const controlsBody = document.getElementById("controls-body");
  const controlsSettingsToggle = document.getElementById("controls-settings-toggle");
  const controlsSettingsBody = document.getElementById("controls-settings-body");
  const structuresToggle = document.getElementById("structures-toggle");
  const structuresBody = document.getElementById("structures-body");
  const projectionsToggle = document.getElementById("projections-toggle");
  const projectionsBody = document.getElementById("projections-body");
  const receptorsToggle = document.getElementById("receptors-toggle");
  const receptorsBody = document.getElementById("receptors-body");
  const drugsToggle = document.getElementById("drugs-toggle");
  const drugsBody = document.getElementById("drugs-body");

  // One collapse-header behaviour shared by the panel, the Controls section and
  // the accordion sections: toggle aria-expanded + the body's hidden flag. The
  // panel + Controls ship expanded, the accordion sections collapsed (their markup
  // sets the initial aria-expanded / hidden).
  // `onToggle(open)` runs after a click so callers can react (accordion below).
  const setSection = (toggle, body, open) => {
    toggle.setAttribute("aria-expanded", String(open));
    body.hidden = !open;
  };
  const wireCollapse = (toggle, body, onToggle) => {
    toggle.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      setSection(toggle, body, open);
      onToggle?.(open);
    });
  };
  // The panel covers the centered brain, so while it is expanded we push the
  // rendered brain clear of it (a render-time camera view offset, see
  // createCameraFocus.setScreenOffset; collapsing it restores the centered view,
  // eased in focus.tick):
  //   - portrait: the panel spans the full width but only the bottom half (see
  //     the @media rule in index.html), so push the brain straight UP into the
  //     clear top section. The shove is half the panel's height fraction, so the
  //     brain ends up centered in the space above the panel whatever its height.
  //   - landscape: the panel is a full-height left sidebar (up to 25% wide), so
  //     push the brain RIGHT by half the panel's width fraction, so it centres in
  //     the clear space beside the sidebar whatever the sidebar's width.
  const controlsPanel = document.getElementById("controls");
  const portrait = window.matchMedia("(orientation: portrait)");
  const updatePanelPan = () => {
    const open = controlsToggle.getAttribute("aria-expanded") === "true";
    // `offsetHeight` is 0 only when the panel is display:none (the ?ui=0 shots);
    // it stays correct for a position:fixed element, unlike `offsetParent`
    // (which is always null for fixed, so it can't be used as a visibility test).
    const visible = controlsPanel.offsetHeight > 0;
    if (!open || !visible) {
      focus.setScreenOffset(0, 0);
    } else if (portrait.matches) {
      const frac =
        controlsPanel.getBoundingClientRect().height / window.innerHeight;
      focus.setScreenOffset(0, Math.min(0.4, frac / 2));
    } else {
      const frac =
        controlsPanel.getBoundingClientRect().width / window.innerWidth;
      focus.setScreenOffset(Math.min(0.3, frac / 2), 0);
    }
  };
  wireCollapse(controlsToggle, controlsBody, updatePanelPan);
  // Recompute when the orientation flips, and whenever the panel's own size
  // changes (collapsing/expanding, or opening the Legend/About accordion, which
  // changes how far the brain must move). The ResizeObserver also fires once on
  // observe, so the initial expanded panel is handled on load.
  portrait.addEventListener("change", updatePanelPan);
  new ResizeObserver(updatePanelPan).observe(controlsPanel);

  // Controls (the sliders + global scene toggles) is a collapsible section like
  // the others but deliberately NOT part of the accordion below: it toggles
  // independently, so opening it leaves an open content section open (and vice
  // versa) and you can tweak a slider without losing your place. The
  // ResizeObserver above re-runs the pan-aside when its height changes.
  if (controlsSettingsToggle && controlsSettingsBody) {
    wireCollapse(controlsSettingsToggle, controlsSettingsBody);
  }

  // Structures, Projections, Receptors and Drugs behave as an accordion among
  // themselves: only one open at a time (Controls, above, is exempt; the Legend,
  // Sources & provenance and About are now popups, not sections). The panel top
  // (language switch + reset/search row) stays visible throughout; the open section grows to
  // fill the tall sidebar via the :has(...) CSS in index.html, so no JS layout
  // class is needed here anymore.
  const sections = [
    { toggle: structuresToggle, body: structuresBody },
    { toggle: projectionsToggle, body: projectionsBody },
    { toggle: receptorsToggle, body: receptorsBody },
    { toggle: drugsToggle, body: drugsBody },
  ];
  for (const s of sections) {
    if (!s.toggle || !s.body) continue;
    wireCollapse(s.toggle, s.body, (open) => {
      // Opening one section closes the others (single-open accordion).
      if (open) {
        for (const other of sections) {
          if (other !== s && other.toggle && other.body) {
            setSection(other.toggle, other.body, false);
          }
        }
      }
    });
  }

  // About: point the "Source code" link at the configured sourceUrl (from
  // app-config.js, default the public site). Drop the row if it isn't a valid
  // http(s) url, so a broken/empty config never shows a dead link.
  const aboutSource = document.getElementById("about-source");
  const sourceUrl = String((window.__APP_CONFIG__ || {}).sourceUrl || "").trim();
  const sourceIsUrl = /^https?:\/\//i.test(sourceUrl);
  if (aboutSource) {
    if (sourceIsUrl) aboutSource.href = sourceUrl;
    else document.getElementById("about-source-row")?.remove();
  }

  // The same source-repo link inside the About "data files" dropdown: point it at
  // sourceUrl too, dropping its row when the config isn't a valid http(s) url (no
  // repo/username hardcoded; the data-file links beside it are same-origin so they
  // always work regardless of this).
  const aboutSource2 = document.getElementById("about-source2");
  if (aboutSource2) {
    if (sourceIsUrl) aboutSource2.href = sourceUrl;
    else document.getElementById("about-source2-row")?.remove();
  }

  // "open an issue" link (embedded in the about.issues paragraph by i18n): point
  // it at the source repo's issues page (sourceUrl + "/issues"), deriving it from
  // the same env-configured sourceUrl so no repo/username is hardcoded. Only do
  // this when sourceUrl points *into* a repository (has a path beyond the host):
  // the committed default is the bare public-site domain, where "/issues" would
  // 404, so there we drop the whole row instead of shipping a dead link. The repo
  // URL is set via the SOURCE_URL env var in the container (see app-config.js).
  const aboutIssues = document.getElementById("about-issues");
  if (aboutIssues) {
    let issuesUrl = "";
    if (sourceIsUrl) {
      try {
        const u = new URL(sourceUrl);
        if (u.pathname.replace(/\/+$/, "") !== "") { // a repo path, not a bare domain
          issuesUrl = `${sourceUrl.replace(/\/+$/, "")}/issues`;
        }
      } catch { /* malformed url: leave the row removed below */ }
    }
    if (issuesUrl) aboutIssues.href = issuesUrl;
    else document.getElementById("about-issues-row")?.remove();
  }

  controls.autoRotate = autorotate.checked;
  controls.autoRotateSpeed = 1.5;
  autorotate.addEventListener("change", () => {
    controls.autoRotate = autorotate.checked;
  });

  // "See inside": hide the near hemisphere so the deep structures show through.
  cull.setEnabled(seeInside.checked);
  seeInside.addEventListener("change", () => cull.setEnabled(seeInside.checked));

  // "Animations": the checkbox reflects the persisted animSettings state (default
  // on for desktop, off for a phone / reduced-motion). Flipping it flows through
  // animSettings, whose subscribers (in main()) stop/allow the decorative motion.
  toggleAnimations.checked = animSettings.enabled;
  toggleAnimations.addEventListener("change", () =>
    animSettings.setEnabled(toggleAnimations.checked));

  // Apply an explode `amount`: spread the regions, keep a focused structure
  // centered (re-aim), and pull the camera to hold the apparent size. Shared by the
  // slider handler and the auto-spread tween so both behave identically.
  // Re-trim arrows precisely once the spread settles (the per-frame updates below
  // are cheap/approximate; see createArrowRetrim). Advanced by its tick() in the
  // render loop.
  const arrowRetrim = createArrowRetrim(arrows);
  const applyExplodeAmount = (amount) => {
    applyExplode(meshes, amount, arrows, true); // fast: reuse cached surface trims
    // Keep a double-clicked / searched structure centered as it blows outward,
    // by re-aiming (rotating) the camera rather than translating it.
    focus.reaimFocused();
    // Pull the camera back as the regions spread (and zoom back in as they
    // reassemble) so the exploded layout stays framed.
    focus.zoomForExplode(amount);
    arrowRetrim.markDirty(); // schedule the precise re-trim for when the spread stops
  };
  const onExplode = () => applyExplodeAmount(parseFloat(explode.value));
  explode.addEventListener("input", onExplode);

  // Auto-spread: focusing a deep (non-lobe) structure from search / a detail panel
  // blows the brain fully apart so the structure isn't buried under the cortex.
  // A manual slider grab cancels it (so the user always wins).
  const autoSpread = createAutoSpread({ slider: explode, apply: applyExplodeAmount });
  explode.addEventListener("input", () => autoSpread.cancel());
  // True when a focused set contains anything that isn't an outer lobe, i.e. a
  // structure that would otherwise sit hidden inside the assembled brain.
  const hasDeep = (meshList) =>
    meshList.some((m) => m && m.userData.structure && m.userData.structure.group !== "lobe");
  const autoSpreadIfDeep = (meshList) => {
    if (hasDeep(meshList)) autoSpread.spreadTo(1);
  };

  // Shift + wheel drives the Separate slider instead of zooming the camera. The
  // capture-phase window listener runs *before* OrbitControls' own wheel handler
  // on the canvas, so swallowing the event here (preventDefault + stopPropagation)
  // stops OrbitControls from also zooming. We dispatch the slider's "input" event
  // rather than calling onExplode directly, so its other listeners fire too
  // (notably the intro-animation cancel). A plain wheel (no shift) is ignored here
  // and falls through to OrbitControls zoom as usual.
  window.addEventListener(
    "wheel",
    (e) => {
      if (!e.shiftKey) return;
      e.preventDefault();
      e.stopPropagation();
      const current = parseFloat(explode.value);
      const step = (e.deltaY < 0 ? 1 : -1) * 0.06; // scroll up = more separation
      const next = Math.min(1, Math.max(0, current + step));
      if (next === current) return; // already at an end stop
      explode.value = String(next);
      explode.dispatchEvent(new Event("input"));
    },
    { capture: true, passive: false }
  );

  // Opacity is owned by the selection controller so the slider value and the
  // isolate-mode dimming compose into one final opacity per structure/arrow.
  const onTransparency = () =>
    selection.setBaseOpacity(parseFloat(transparency.value));
  transparency.addEventListener("input", onTransparency);

  // Button that forces structure labels on/off at once (vs. hover, which shows
  // just one). When something is selected (an isolated region, a circuit, a
  // halo'd structure/arrow), it names only the selection rather than every
  // structure, so the focus isn't drowned in labels; with nothing selected it
  // names everything. aria-pressed + an .active class reflect the state.
  // "Show all names" checkbox (next to Auto-rotate): force every structure label
  // on at once (vs. hover, one at a time). When something is selected it names only
  // the selection rather than every structure, so the focus isn't drowned in
  // labels; with nothing selected it names everything. The checkbox's own `checked`
  // is the state (no separate flag).
  const showAllScoped = () => {
    const on = toggleNames.checked;
    const sel = on ? selection.getSelected() : null;
    labels.setShowAll(on, sel?.meshes ?? null, sel?.arrows ?? null);
  };
  toggleNames.addEventListener("change", showAllScoped);
  // Keep the named set tracking the selection while show-all is on, so adding /
  // removing an isolated region (or clearing it) updates which names show.
  selection.onIsolate(showAllScoped);

  // "Show projections" checkbox (next to Auto-rotate): show/hide every projection
  // arrow at once (checked by default = arrows shown; unchecking hides them all).
  // projVis refreshes the connection labels (which key off group.visible) and the
  // pick helpers skip hidden groups. Composes with the legend's "Hypothetical
  // pathways" toggle through projVis: hiding wins, and re-showing restores the
  // tentative arrows only if that section is toggled on.
  toggleProjections.addEventListener("change", () => {
    projVis.setAllHidden(!toggleProjections.checked);
  });

  // Apply initial slider values so the scene matches the UI on load.
  onExplode();
  onTransparency();

  // Hand the auto-spread back to the caller: the focus helpers (selectStructure,
  // focusDrug, ...) live in the main scope and call autoSpreadIfDeep, and the
  // render loop advances autoSpread.tick() + arrowRetrim.tick().
  return { autoSpread, autoSpreadIfDeep, arrowRetrim };
}

/**
 * Hemisphere tag for a connection, derived from its endpoint ids, so the two
 * mirrored copies of a pathway (and the cross-midline commissures) are
 * distinguishable in the search list (which matches on the bare label).
 * @param {object} proj
 * @returns {string} "R", "L", "L↔R", or "" (purely midline).
 */
function connectionSideTag(proj) {
  const right = proj.from.endsWith("_R") || proj.to.endsWith("_R");
  const left = proj.from.endsWith("_L") || proj.to.endsWith("_L");
  if (left && right) return "L↔R";
  if (right) return "R";
  if (left) return "L";
  return "";
}

/**
 * Wire the panel's reset + search buttons (the row just above the sliders): a
 * reset button that recenters the view (handy after panning has slid the brain
 * off-center), and a magnifier that swaps a search box in place of the panel's
 * normal controls. Typing filters structures (by name), connections (by pathway
 * label) and receptors (by name / neurotransmitter / system); clicking a result
 * (or pressing Enter to take the first one) frames the camera on it. A structure
 * result opens its structure panel, a connection result the connection panel, a
 * receptor/target result focuses it (dim + dots + panel). All go through the
 * shared selectStructure / selectConnection / selectTarget helpers.
 * @param {{focus:ReturnType<typeof createCameraFocus>, meshes:THREE.Mesh[],
 *   arrows:import("./arrows.js").ProjectionArrow[],
 *   data:import("./data.js").BrainData,
 *   selection:ReturnType<typeof createSelection>,
 *   selectStructure:Function, selectConnection:Function,
 *   selectTarget:Function}} deps
 */
function wireToolbar({ focus, meshes, arrows, data, selection, tabs, selectStructure, selectConnection, focusTarget, focusDrug, focusCircuit, focusProjectionGroup }) {
  const resetBtn = document.getElementById("reset-view");
  const searchToggle = document.getElementById("search-toggle");
  const searchBox = document.getElementById("search");
  const searchInput = document.getElementById("search-input");
  const searchClear = document.getElementById("search-clear");
  const searchResults = document.getElementById("search-results");
  // Show the inline clear "×" only when the box holds text. Called from
  // renderResults (which runs on every value change: input, open, prefilled query).
  const syncClear = () => { if (searchClear) searchClear.hidden = !searchInput.value; };
  // The normal controls; the search box shows in their place (not as a popup),
  // while the reset/search buttons above stay put so the magnifier can toggle
  // back.
  const controlsMain = document.getElementById("controls-main");

  resetBtn.addEventListener("click", () => {
    focus.recenter();
    // Full reset: close any open detail tabs (which clears the 3D focus and strips
    // the deep-link hash via setOnEmpty), then drop any remaining halo / isolate set,
    // restoring default opacity.
    tabs.closeAll();
    selection.clear();
  });

  // One searchable index over structures + connections + receptors, each carrying
  // the action to run when it is picked. Built once. Mirrored L/R twins are
  // collapsed to a single row (a brain is symmetric, so "frontal lobe" and
  // "corticothalamic" each list once and a pick focuses *both* hemispheres, not one);
  // receptors show their neurotransmitter as a tag (and carry extra `keywords` so the
  // system / mechanism also match). The match runs over `label` + `keywords`; only
  // `label` is shown.
  const stripSide = (id) => id.replace(/_[LR]$/, "");
  // Group meshes / arrows by their side-stripped base so each pair yields one row.
  const meshesByBase = new Map();
  for (const mesh of meshes) {
    const base = stripSide(mesh.userData.structure.id);
    (meshesByBase.get(base) || meshesByBase.set(base, []).get(base)).push(mesh);
  }
  const arrowsByBase = new Map();
  for (const arrow of arrows) {
    const p = arrow.projection;
    const key = `${stripSide(p.from)}->${stripSide(p.to)}`;
    (arrowsByBase.get(key) || arrowsByBase.set(key, []).get(key)).push(arrow);
  }
  const items = [
    ...[...meshesByBase.values()].map((group) => {
      // Frame a representative (prefer the midline / right member); the isolate
      // already spans both sides via isolateGroupFor, so both hemispheres dim in.
      const rep = group.find((m) => !/_[LR]$/.test(m.userData.structure.id)) || group[0];
      const s = rep.userData.structure;
      return {
        type: "structure",
        // base_name is the hemisphere-stripped name ("frontal lobe"); fall back to
        // the full name for a genuine singleton.
        label: s.base_name || s.name,
        select: () => selectStructure(rep, { frame: true, isolate: true }),
        preview: () => selectStructure(rep, { isolate: true, preview: true }),
      };
    }),
    ...[...arrowsByBase.values()].map((group) => {
      const rep = group[0];
      const proj = rep.projection;
      const siblings = group.slice(1);
      // A clean L/R pair needs no side tag; a lone / crossing pathway keeps its tag.
      const tag = siblings.length ? "" : connectionSideTag(proj);
      return {
        type: "connection",
        label: proj.label + (tag ? ` · ${tag}` : ""),
        // Frame + isolate both twins, so a connection search pick dims the rest of the
        // brain and lights both hemispheres, not just the picked side.
        select: () => selectConnection(rep, { frame: true, isolate: true, siblings }),
        preview: () => selectConnection(rep, { isolate: true, preview: true, siblings }),
      };
    }),
    // Focusable receptors + non-receptor targets (a stub / unlocated target has no
    // anatomy to show, so it stays a legend-only listing). A receptor shows its
    // neurotransmitter as the tag, a target its type; keywords carry the system /
    // mechanism so they match too without cluttering the row.
    ...(data.targets || []).filter((tgt) => tgt.focusable).map((tgt) => {
      const tag = tgt.kind === "receptor"
        ? (tgt.receptor && tgt.receptor.neurotransmitter)
        : tgt.typeLabel;
      return {
        type: "target",
        label: tgt.name + (tag ? ` · ${tag}` : ""),
        keywords: tgt.keywords || "",
        select: () => focusTarget(tgt, { frame: true }),
        preview: () => focusTarget(tgt, { preview: true }),
      };
    }),
    // Focusable drugs (those with a binding profile). The row shows the primary
    // class as a tag; keywords carry the full class list + nomenclature + targets.
    // `fields` feeds the structured `class:"..."` / `nbn:"..."` filters (the panel's
    // clickable Class / Nomenclature values), pre-folded for matching.
    ...(data.drugs || []).filter((d) => d.focusable).map((drug) => ({
      type: "drug",
      label: drug.name + (drug.category ? ` · ${drug.category}` : ""),
      keywords: drug.keywords || "",
      fields: {
        class: foldText(drug.categoryLabels.join(" ")),
        nbn: foldText(drug.nbn || ""),
      },
      select: () => focusDrug(drug, { frame: true }),
      preview: () => focusDrug(drug, { preview: true }),
    })),
    // Named circuits (the loops in the Projections section): a pick isolates the
    // loop, plays its traveling pulse and opens its panel, exactly like its legend
    // row, so search reaches them too (part of "anything from search == the panel").
    ...(data.circuits || []).map((circuit) => ({
      type: "circuit",
      label: `${circuit.name} · ${t("search.tagCircuit")}`,
      keywords: circuit.description || "",
      select: () => focusCircuit(circuit, { frame: true }),
      preview: () => focusCircuit(circuit, { preview: true }),
    })),
    // Projection groups (the per-transmitter / per-sign rows of the Projections
    // legend): a pick pins that whole pathway group + dims the rest + opens its
    // panel, like its legend row. Both colour modes' records are listed; their
    // names don't collide (transmitters vs excitatory/inhibitory/modulatory).
    ...(data.projectionGroups || []).map((group) => ({
      type: "group",
      label: `${group.name} · ${t("search.tagPathways")}`,
      keywords: group.description || "",
      select: () => focusProjectionGroup(group, { frame: true }),
      preview: () => focusProjectionGroup(group, { preview: true }),
    })),
  ];

  // Type-filter chips above the results: scope the search to one kind of thing
  // (a structure, a drug, ...). The label reuses each section's own heading so the
  // chip can't drift from the panel. Only types actually present become chips, plus
  // an "All" reset; `activeType` (null = all) persists for the session like the
  // query text does. Built once (the item set is static).
  const searchFilters = document.getElementById("search-filters");
  const FILTER_LABELS = {
    structure: "panel.structures", connection: "info.connections",
    target: "panel.receptors", drug: "panel.drugs",
    circuit: "legend.circuits", group: "legendKey.pathways",
  };
  let activeType = null;
  const filterChips = [];
  const presentTypes = [...new Set(items.map((it) => it.type))]
    .filter((ty) => ty in FILTER_LABELS);
  if (searchFilters && presentTypes.length > 1) {
    const addChip = (type, labelKey) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "search-filter" + (type === activeType ? " active" : "");
      b.textContent = t(labelKey);
      b.addEventListener("click", () => {
        activeType = type;
        for (const c of filterChips) c.el.classList.toggle("active", c.type === activeType);
        renderResults();
        searchInput.focus();
      });
      searchFilters.appendChild(b);
      filterChips.push({ type, el: b });
    };
    addChip(null, "search.filterAll");
    for (const ty of presentTypes) addChip(ty, FILTER_LABELS[ty]);
  }

  // Index (among the non-empty rows) of the keyboard-highlighted result, or -1
  // when there is none. Arrow keys move it; Enter activates it (the first by
  // default, since renderResults pre-highlights row 0).
  let activeIndex = -1;
  // True while a hover preview (a transient focus, see the row mouseenter) is
  // applied but not yet committed by a click. Leaving the result list restores the
  // brain to neutral; a click clears the flag so the committed focus survives.
  let previewing = false;
  searchResults.addEventListener("mouseleave", () => {
    if (previewing) { previewing = false; selection.clear(); }
  });
  const resultRows = () => [...searchResults.querySelectorAll("li:not(.empty)")];
  function highlight(index) {
    const rows = resultRows();
    if (rows.length === 0) { activeIndex = -1; return; }
    activeIndex = (index + rows.length) % rows.length; // wrap past either end
    rows.forEach((li, i) => li.classList.toggle("active", i === activeIndex));
    rows[activeIndex].scrollIntoView({ block: "nearest" });
  }

  // Rebuild the (capped) result list from the current query. An empty query
  // lists everything so the box doubles as a browsable index.
  function renderResults() {
    // Parse a leading `field:"value"` filter (else plain free text). A field filter
    // keeps only items carrying that field whose value matches; the trailing free
    // text still matches the label + keywords.
    const { field, value, rest } = parseSearchQuery(searchInput.value);
    syncClear();
    searchResults.innerHTML = "";
    // A structured filter (class:"..." / nbn:"...") is a deliberate "list the whole
    // class" query, so show more rows than the compact name-search list (the results
    // box scrolls). Plain name search stays capped short.
    const cap = field ? 40 : 8;
    // Score each surviving item so the most relevant rise to the top of the capped
    // list: a label that *starts with* the query beats one that merely contains it,
    // which beats a keyword-only match. Without this, array order alone buried the
    // late entries (circuits, projection groups) under a common query like
    // "dopamine". An empty query (browse-all) and field-only filters leave `rest`
    // empty -> every item scores 0 -> the stable `idx` tiebreak keeps the original
    // order (structures first).
    const scored = [];
    items.forEach((it, idx) => {
      if (activeType && it.type !== activeType) return; // type chip scopes the list
      if (field) {
        const fv = it.fields && it.fields[field];
        if (fv === undefined) return; // only items carrying this field
        if (value && !fv.includes(value)) return;
      }
      let score = 0;
      if (rest) {
        const label = foldText(it.label);
        if (label.startsWith(rest)) score = 0;
        else if (label.includes(rest)) score = 1;
        else if (foldText(it.keywords || "").includes(rest)) score = 2;
        else return; // no match in label or keywords
      }
      scored.push({ it, score, idx });
    });
    scored.sort((a, b) => a.score - b.score || a.idx - b.idx);
    const matches = scored.slice(0, cap).map((s) => s.it);
    if (matches.length === 0) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = t("search.noMatch");
      searchResults.appendChild(li);
      activeIndex = -1;
      return;
    }
    matches.forEach((item, i) => {
      const li = document.createElement("li");
      li.textContent = item.label;
      li.addEventListener("click", () => {
        previewing = false; // the pick is now the committed focus, not a preview
        item.select();
        closeSearch();
      });
      // Hovering syncs the highlight (so mouse + keyboard agree on the active row)
      // AND transiently applies the row's full focus, so you can dim the brain down
      // to each result in turn to compare them without committing. Restored when the
      // pointer leaves the list (the #search-results mouseleave below).
      li.addEventListener("mouseenter", () => {
        highlight(i);
        if (item.preview) { item.preview(); previewing = true; }
      });
      searchResults.appendChild(li);
    });
    highlight(0); // pre-highlight the first match: Enter selects it straight away
  }

  // The search box lives inside the (collapsible) panel body, so opening search
  // from the Ctrl/Cmd+F shortcut must also expand a collapsed panel, otherwise
  // the box would be revealed inside a hidden body. Done by DOM here (the panel
  // collapse lives in wireControls, a separate scope).
  const controlsToggle = document.getElementById("controls-toggle");
  const controlsBody = document.getElementById("controls-body");
  function ensurePanelOpen() {
    if (controlsToggle && controlsBody && controlsBody.hidden) {
      controlsToggle.setAttribute("aria-expanded", "true");
      controlsBody.hidden = false;
    }
  }

  function openSearch() {
    ensurePanelOpen();
    // The search box lives in the Settings pane; if a detail's Details tab is
    // active, switch back so the box is actually visible (the detail stays
    // available behind the tab).
    tabs.showSettings();
    controlsMain.hidden = true; // swap the sliders/legend out...
    searchBox.hidden = false; // ...and the search in, in their place
    searchToggle.classList.add("active");
    // Keep whatever was last typed this session: the input retains its value while
    // hidden, and a page reload (a new session) starts it empty, so this is
    // session-scoped memory with no persistence. Re-render the matching results for
    // the remembered query and select all of it, so the next keystroke replaces it
    // while Enter / arrow-browsing the existing results still works straight away.
    renderResults();
    searchInput.focus();
    searchInput.select();
  }
  function closeSearch() {
    searchBox.hidden = true;
    controlsMain.hidden = false;
    searchToggle.classList.remove("active");
  }

  // Open search pre-filled with a query (a drug panel's clickable Class /
  // Nomenclature hands back e.g. `class:"SNRI"`), so the structured filter runs
  // immediately. Works whether search was open or closed.
  function openSearchWithQuery(query) {
    if (searchBox.hidden) openSearch();
    else tabs.showSettings(); // ensure the Settings pane (which holds the box) shows
    searchInput.value = query;
    renderResults();
    searchInput.focus();
  }

  // The "?" button toggles the search-syntax help block beneath the bar.
  const searchHelp = document.getElementById("search-help");
  const searchSyntax = document.getElementById("search-syntax");
  if (searchHelp && searchSyntax) {
    searchHelp.addEventListener("click", () => {
      const show = searchSyntax.hidden;
      searchSyntax.hidden = !show;
      searchHelp.setAttribute("aria-expanded", String(show));
    });
  }

  searchToggle.addEventListener("click", () => {
    if (searchBox.hidden) openSearch();
    else closeSearch();
  });
  searchInput.addEventListener("input", renderResults);
  // The inline "×": wipe the query, re-render (now empty -> the neutral list) and
  // keep focus so the user can retype immediately; syncClear (in renderResults)
  // hides the button again.
  if (searchClear) {
    searchClear.addEventListener("click", () => {
      searchInput.value = "";
      renderResults();
      searchInput.focus();
    });
  }
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      highlight(activeIndex + 1);
      event.preventDefault(); // don't move the text caret
    } else if (event.key === "ArrowUp") {
      highlight(activeIndex - 1);
      event.preventDefault();
    } else if (event.key === "Enter") {
      const rows = resultRows();
      const pick = rows[activeIndex] || rows[0]; // highlighted, else the first
      if (pick) pick.click();
    } else if (event.key === "Escape") {
      closeSearch();
    }
  });

  // Ctrl/Cmd+F opens our in-panel search instead of the browser's native find
  // (which would be useless here: the structures/connections are canvas + data,
  // not page text). If search is already open we just re-focus and select its
  // text so a second press lets the user retype straight away.
  window.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && (event.key === "f" || event.key === "F")) {
      event.preventDefault();
      if (searchBox.hidden) {
        openSearch();
      } else {
        // Already open: make sure the Settings pane (which holds the box) is the
        // visible tab, then refocus + select so a second press lets the user
        // retype straight away.
        tabs.showSettings();
        searchInput.focus();
        searchInput.select();
      }
    }
  });

  return { openSearchWithQuery };
}

/**
 * Global single-key shortcuts (no modifier), ignored while typing in a field.
 * Each maps to an existing control by clicking the same DOM element a mouse user
 * would (or nudging the Separate slider), so there is no duplicated behaviour:
 *   n  toggle all names            l  collapse / expand the Legend section
 *   s  spread fully / collapse     c  toggle "See inside"
 *   r  open Receptors & targets    m  open the Drugs (meds) section
 *   f  open search (bare-key Ctrl/Cmd+F)   Tab  cycle the detail tabs
 *   ?  open the shortcuts popup
 *   Esc  close popup, else close search + collapse any open Legend/Receptors/About
 * (Reset has no key: it is the centered toolbar button, so r is free for the
 * Receptors section, matching m for the Drugs section.)
 * Ctrl/Cmd+F (search) stays handled in wireToolbar; here `f` is its bare-key
 * twin. preventDefault on a handled key stops `f` typing into the search box it
 * just focused (and any other stray default). `help` is the shortcuts-popup
 * controller (wireShortcutsHelp): when its dialog is open Esc closes that first.
 * `selection` lets Esc clear an active focus (isolate / circuit / drug-or-receptor
 * dim) so the brain returns to its plain state, see the Escape case. `lightbox` is
 * the image popup: when it is open Esc closes it before anything else.
 */
function wireShortcuts(help, tabs, selection, lightbox, aboutModal, legendModal, sourcingModal) {
  const click = (id) => document.getElementById(id)?.click();
  const isTyping = (el) =>
    !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA"
      || el.tagName === "SELECT" || el.isContentEditable);

  // Separate slider: fully spread if collapsed, else back to assembled. Dispatch
  // "input" (not a direct call) so its other listeners fire too (the intro
  // cancel, the camera re-aim + explode zoom), like the shift+wheel handler.
  const toggleSpread = () => {
    const explode = document.getElementById("explode");
    if (!explode) return;
    explode.value = parseFloat(explode.value) > 0 ? "0" : "1";
    explode.dispatchEvent(new Event("input"));
  };

  // Esc closes the in-panel search and collapses any open accordion section, by
  // clicking the same toggles a user would so the existing wiring runs. (The
  // Legend is a Controls sub-panel, not an accordion peer, so Esc leaves it be.)
  const collapseOpen = () => {
    const search = document.getElementById("search");
    if (search && !search.hidden) click("search-toggle");
    for (const id of ["structures-toggle", "projections-toggle", "receptors-toggle",
                      "drugs-toggle"]) {
      const tg = document.getElementById(id);
      if (tg && tg.getAttribute("aria-expanded") === "true") tg.click();
    }
    sectionNav.reset(); // a closed section keeps no stale keyboard highlight
  };

  // Open search only (never toggle it back off), matching Ctrl/Cmd+F.
  const openSearch = () => {
    const search = document.getElementById("search");
    if (search && search.hidden) click("search-toggle");
  };

  // "k": toggle the Legend popup (its colour/symbol key). It is now a modal, so a
  // press opens it and a second press closes it.
  const toggleLegend = () => {
    if (!legendModal) return;
    if (legendModal.isOpen) legendModal.close();
    else legendModal.open();
  };

  // Roving keyboard navigation inside the currently-open accordion section: once
  // a section is open (e.g. after `l` opens the Legend), ArrowDown / ArrowUp move
  // a highlight (`.kbd-active`) through that section's interactive rows (its
  // action buttons + every `.clickable` row/heading) and Enter activates the
  // highlighted one (a plain click, so it isolates / focuses / opens its detail
  // tab exactly as a mouse click would). Rows are recomputed on each key (the
  // legend rebuilds, the drug filter hides rows), and the highlight is dropped
  // when the open section changes or closes. No-op when no section is open, so
  // the arrow/Enter keys keep their default behaviour elsewhere.
  const sectionNav = (() => {
    const BODIES = [
      ["structures-toggle", "structures-body"],
      ["projections-toggle", "projections-body"],
      ["receptors-toggle", "receptors-body"],
      ["drugs-toggle", "drugs-body"],
    ];
    let activeEl = null;
    let lastBody = null;
    const openBody = () => {
      for (const [tid, bid] of BODIES) {
        const tg = document.getElementById(tid);
        if (tg && tg.getAttribute("aria-expanded") === "true") {
          return document.getElementById(bid);
        }
      }
      return null;
    };
    const rows = (body) =>
      [...body.querySelectorAll("button, .clickable")]
        .filter((el) => el.offsetParent !== null && !el.disabled);
    const setActive = (el, list) => {
      for (const r of list) r.classList.toggle("kbd-active", r === el);
      activeEl = el || null;
      if (el) el.scrollIntoView({ block: "nearest" });
    };
    return {
      handle(key) {
        const body = openBody();
        if (body !== lastBody) {
          // Section changed or closed: drop the stale highlight on the old body.
          if (lastBody) {
            for (const r of lastBody.querySelectorAll(".kbd-active")) {
              r.classList.remove("kbd-active");
            }
          }
          activeEl = null;
          lastBody = body;
        }
        if (!body) return false;
        const list = rows(body);
        if (list.length === 0) return false;
        if (key === "Enter") {
          if (activeEl && list.includes(activeEl)) { activeEl.click(); return true; }
          return false; // nothing highlighted yet: leave Enter alone
        }
        let idx = list.indexOf(activeEl);
        if (key === "ArrowDown") idx = idx < 0 ? 0 : (idx + 1) % list.length;
        else idx = idx <= 0 ? list.length - 1 : idx - 1; // ArrowUp, wraps
        setActive(list[idx], list);
        return true;
      },
      // Drop any highlight everywhere (called when a section is toggled via the
      // keyboard, so opening/closing/switching a section never leaves a stale
      // outline behind on a now-hidden body).
      reset() {
        for (const [, bid] of BODIES) {
          const body = document.getElementById(bid);
          if (body) {
            for (const r of body.querySelectorAll(".kbd-active")) {
              r.classList.remove("kbd-active");
            }
          }
        }
        activeEl = null;
        lastBody = null;
      },
    };
  })();

  window.addEventListener("keydown", (event) => {
    if (event.ctrlKey || event.metaKey || event.altKey) return; // leave combos alone
    if (isTyping(event.target)) return; // let the field keep the key (Esc self-handles)
    // With any popup open, Esc just closes it (and nothing else fires). The image
    // lightbox is checked first so it wins when stacked over another (it can be
    // opened from a panel behind a modal). Only one popup is open at a time.
    if (event.key === "Escape") {
      for (const modal of [lightbox, help, aboutModal, legendModal, sourcingModal]) {
        if (modal?.isOpen) {
          modal.close();
          event.preventDefault();
          return;
        }
      }
    }
    // Tab / Shift+Tab cycle the detail tabs (incl. the pinned Settings tab). Only
    // swallow the key when there is something to cycle, so with no detail open
    // Tab keeps its default focus-move behaviour.
    if (event.key === "Tab") {
      if (tabs && tabs.cycle(event.shiftKey ? -1 : 1)) event.preventDefault();
      return;
    }
    // Arrow keys / Enter browse + activate the rows of the open accordion section
    // (Legend / Receptors / Drugs); only swallowed when a section actually handled
    // them, so they keep their default behaviour with no section open.
    if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Enter") {
      if (sectionNav.handle(event.key)) event.preventDefault();
      return;
    }
    switch (event.key) {
      case "?": help?.open(); break;
      case "n": case "N": click("toggle-names"); break;
      case "s": case "S": toggleSpread(); break;
      case "l": case "L": sectionNav.reset(); click("structures-toggle"); break;
      case "p": case "P": sectionNav.reset(); click("projections-toggle"); break;
      case "k": case "K": toggleLegend(); break;
      case "c": case "C": click("see-inside"); break;
      case "r": case "R": sectionNav.reset(); click("receptors-toggle"); break;
      case "m": case "M": sectionNav.reset(); click("drugs-toggle"); break;
      case "f": case "F": openSearch(); break;
      // Esc peels one layer at a time, prioritizing a return to the plain brain:
      // (1) close the active detail tab (which clears its dim when it is the last
      // tab), else (2) clear any active focus/isolate/circuit so the brain is
      // un-dimmed with nothing hidden, else (3) close search / collapse an open
      // section. So a focus made from a legend row (a circuit / projection-group /
      // structure isolate that opens no tab) is also cleared by Esc, not just a
      // drug/receptor detail tab.
      case "Escape":
        if (tabs && tabs.closeActive()) break;
        if (selection && selection.getSelected()) { selection.clear(); break; }
        collapseOpen();
        break;
      default: return; // unhandled key: leave its default intact
    }
    event.preventDefault();
  });
}

/**
 * Keyboard-shortcuts help popup (#shortcuts-modal). Fills the key -> action rows
 * from the i18n catalogue (so each language reads right) and returns a small
 * controller; wireShortcuts opens it on `?` and closes it on Esc, the toolbar's
 * keyboard button opens it, and the ×, a backdrop click, or Esc close it.
 * @returns {{open:()=>void, close:()=>void, isOpen:boolean}}
 */
function wireShortcutsHelp() {
  const modal = document.getElementById("shortcuts-modal");
  const list = document.getElementById("shortcuts-list");
  const noop = { open() {}, close() {}, get isOpen() { return false; } };
  if (!modal || !list) return noop;

  // One row per shortcut, mirroring the keys wired in wireShortcuts so the popup
  // can't drift from the actual bindings. The label is a localized action.
  const ROWS = [
    { keys: ["N"], desc: "shortcuts.names" },
    { keys: ["S"], desc: "shortcuts.spread" },
    { keys: ["L"], desc: "shortcuts.structures" },
    { keys: ["P"], desc: "shortcuts.projections" },
    { keys: ["K"], desc: "shortcuts.legend" },
    { keys: ["C"], desc: "shortcuts.seeInside" },
    { keys: ["R"], desc: "shortcuts.receptors" },
    { keys: ["M"], desc: "shortcuts.drugs" },
    { keys: ["F"], desc: "shortcuts.search" },
    { keys: ["Tab"], desc: "shortcuts.tabs" },
    { keys: ["Esc"], desc: "shortcuts.close" },
  ];
  for (const r of ROWS) {
    const dt = document.createElement("dt");
    for (const k of r.keys) {
      const kbd = document.createElement("kbd");
      kbd.textContent = k;
      dt.appendChild(kbd);
    }
    const dd = document.createElement("dd");
    dd.textContent = t(r.desc);
    list.append(dt, dd);
  }

  return wireModal({ modalId: "shortcuts-modal", toggleId: "shortcuts-toggle", closeId: "shortcuts-close" });
}

/**
 * Shared wiring for a simple .modal-overlay popup (About / Legend / Sources &
 * provenance / the shortcuts help): a toggle button opens it, the × and a click on
 * the dimmed backdrop close it, and it exposes {open, close, isOpen} so
 * wireShortcuts can route Esc. `onOpen` (optional) runs just before it shows.
 * Returns a no-op controller when the modal element is absent.
 * @returns {{open:()=>void, close:()=>void, isOpen:boolean}}
 */
function wireModal({ modalId, toggleId, closeId, onOpen }) {
  const modal = document.getElementById(modalId);
  const noop = { open() {}, close() {}, get isOpen() { return false; } };
  if (!modal) return noop;
  const close = () => { modal.hidden = true; };
  const open = () => { onOpen?.(); modal.hidden = false; };
  if (toggleId) document.getElementById(toggleId)?.addEventListener("click", open);
  if (closeId) document.getElementById(closeId)?.addEventListener("click", close);
  modal.addEventListener("click", (event) => { if (event.target === modal) close(); });
  return { open, close, get isOpen() { return !modal.hidden; } };
}

/**
 * About popup (#about-modal): the project blurb + source / issues / licence /
 * attribution links. Opened by the toolbar's info button; the ×, a backdrop click,
 * or Esc close it. Its bottom "Sources & provenance" link closes this and opens the
 * #sourcing-modal (passed in). Prose + href wiring live in the markup + wireControls.
 * @returns {{open:()=>void, close:()=>void, isOpen:boolean}}
 */
function wireAboutModal(sourcing) {
  const ctrl = wireModal({ modalId: "about-modal", toggleId: "about-toggle", closeId: "about-close" });
  document.getElementById("about-open-sourcing")?.addEventListener("click", (event) => {
    event.preventDefault();
    ctrl.close();
    sourcing?.open();
  });
  return ctrl;
}

/**
 * Legend popup (#legend-modal): the static colour/symbol key (built by
 * buildLegendKey into #legend-body). Opened by the toolbar legend button or the k
 * key; the ×, a backdrop click, or Esc close it. Its bottom "Sources & provenance"
 * link closes this and opens the #sourcing-modal (passed in).
 * @returns {{open:()=>void, close:()=>void, isOpen:boolean}}
 */
function wireLegendModal(sourcing) {
  const ctrl = wireModal({ modalId: "legend-modal", toggleId: "legend-toggle", closeId: "legend-close" });
  document.getElementById("legend-open-sourcing")?.addEventListener("click", (event) => {
    event.preventDefault();
    ctrl.close();
    sourcing?.open();
  });
  return ctrl;
}

/**
 * Sources & provenance popup (#sourcing-modal): the grade key + coverage tally
 * (built by buildAboutSourcing into #about-sourcing). Opened by its own toolbar
 * button, from the Legend + About popups, and auto-shown over the loading overlay
 * on startup (see main()). The ×, a backdrop click, or Esc close it.
 * @returns {{open:()=>void, close:()=>void, isOpen:boolean}}
 */
function wireSourcingModal() {
  return wireModal({ modalId: "sourcing-modal", toggleId: "sourcing-toggle", closeId: "sourcing-close" });
}

/**
 * Image lightbox (#image-lightbox): pops a clicked structure illustration or
 * molecule diagram up large over a dimmed backdrop. `open(src, alt, {invert})`
 * shows an image (`invert` mirrors the molecule line-art inversion so it reads on
 * the dark backdrop); the ×, a backdrop click, or Esc (routed by wireShortcuts)
 * close it. Reuses the shared .modal-overlay styling.
 * @returns {{open:(src:string, alt?:string, opts?:{invert?:boolean})=>void,
 *   close:()=>void, isOpen:boolean}}
 */
function wireImageLightbox() {
  const overlay = document.getElementById("image-lightbox");
  const img = document.getElementById("image-lightbox-img");
  const closeBtn = document.getElementById("image-lightbox-close");
  const noop = { open() {}, close() {}, get isOpen() { return false; } };
  if (!overlay || !img) return noop;
  const MAX_UPSCALE = 4; // how far a small source may be blown up (readability > crispness)
  // Size the image to fill most of the viewport: enlarge a small thumbnail (the
  // point of the lightbox) but never past the viewport, and cap the upscale so a
  // tiny raster doesn't turn into a wall of blur. Vector SVGs scale crisply.
  const sizeToViewport = () => {
    const nw = img.naturalWidth, nh = img.naturalHeight;
    if (!nw || !nh) { img.style.width = img.style.height = ""; return; }
    const scale = Math.min(
      (window.innerWidth * 0.92) / nw, (window.innerHeight * 0.92) / nh, MAX_UPSCALE);
    img.style.width = Math.round(nw * scale) + "px";
    img.style.height = Math.round(nh * scale) + "px";
  };
  const close = () => {
    overlay.hidden = true;
    img.removeAttribute("src"); // drop the (possibly multi-MB) decode while closed
    img.style.width = img.style.height = "";
  };
  const open = (src, alt, { invert = false } = {}) => {
    if (!src) return;
    img.onload = sizeToViewport;
    img.src = src;
    img.alt = alt || "";
    img.classList.toggle("inverted", invert);
    overlay.hidden = false;
    if (img.complete && img.naturalWidth) sizeToViewport(); // cached: load won't refire
  };
  closeBtn?.addEventListener("click", close);
  // A click anywhere but the image itself (the dimmed backdrop / the ×) closes it.
  overlay.addEventListener("click", (event) => {
    if (event.target !== img) close();
  });
  return { open, close, get isOpen() { return !overlay.hidden; } };
}

async function main() {
  const { scene, camera, renderer, controls, baseDpr } = initThree();

  // Stamp the version into the panel header (single source: window.__APP_VERSION__
  // from version.js). Done before the data load so it shows even if that fails.
  const versionEl = document.getElementById("app-version");
  if (versionEl && window.__APP_VERSION__) {
    versionEl.textContent = `v${window.__APP_VERSION__}`;
  }

  // Startup loading overlay (the #loading element, visible by default): a progress
  // bar over the canvas so a slow first load shows feedback. Fetch fills the first
  // ~half of the bar, SDF meshing the rest (see below); done() fades it out.
  const loading = createLoadingScreen();
  loading.setProgress(0.02, t("loading.data"));

  // Sources & provenance popup (the startup gate): wire it + fill its static parts
  // (intro + grade key) now and show it over the still-visible loading overlay (it
  // sits above it via a higher z-index, see the CSS). A visitor reads how the data
  // is sourced while the app loads and closes it to continue (the app may still be
  // loading behind it, or already up). Its coverage tally needs the loaded dataset,
  // so it is filled in below once data arrives. Skipped for the clean-shot ?ui=0
  // mode (screenshots / deep links). The Legend + About popups reference this
  // controller (their "Sources & provenance" links open it), so it is created here.
  const sourcingModal = wireSourcingModal();
  buildAboutSourcing(null);
  if (new URLSearchParams(window.location.search).get("ui") !== "0") sourcingModal.open();

  let data;
  try {
    data = await loadBrainData("data", (p) => {
      // Fill the sourcing gate's coverage bars as soon as meta lands (before the
      // slow shape/mesh phase), so a visitor watching the load sees the sourcing
      // coverage, not just the intro text.
      if (p.stage === "meta-ready" && p.meta?.provenance_stats) {
        buildAboutSourcing({ provenanceStats: p.meta.provenance_stats });
      }
      if (p.stage === "shapes" && p.total) {
        loading.setProgress(0.05 + 0.45 * (p.loaded / p.total), t("loading.shapes"));
      }
    });
  } catch (err) {
    console.error(err);
    loading.fail(); // drop the overlay; the error shows as a banner
    window.showErrorBanner?.(t("status.loadError", { msg: err.message }));
    return;
  }

  // Mesh the SDF shapes off the main thread (a small Web Worker pool), so
  // assembling the brain's ~40 SDF meshes at load never freezes the page. The
  // cheap shapes (blob/curve/composite) stay synchronous. The pool falls back to
  // synchronous meshing per-spec if workers are unavailable (see js/sdf-pool.js),
  // so the brain always renders; this is a pure performance path.
  const sdfItems = data.structures
    .filter((s) => s.shape && s.shape.type === "sdf")
    .map((s) => ({ id: s.id, spec: s.shape }));
  const pool = createSdfPool();
  let sdfGeoms = new Map();
  try {
    sdfGeoms = await pool.meshAll(sdfItems, (id, done, total) => {
      // Meshing fills the back half of the bar; name the region as it lands.
      const name = data.byId.get(id)?.base_name || id;
      loading.setProgress(0.5 + 0.45 * (done / total), t("loading.meshing", { name }));
    });
  } catch (err) {
    console.warn("sdf pool meshing failed; falling back to synchronous", err);
  } finally {
    pool.dispose(); // geometry is built once at load; free the workers after
  }

  // Build region meshes and index them for the arrows. SDF structures get their
  // pre-meshed geometry; everything else is meshed synchronously inside the call.
  const meshes = [];
  const meshById = new Map();
  for (const structure of data.structures) {
    const mesh = buildStructureMesh(structure, sdfGeoms.get(structure.id));
    meshes.push(mesh);
    meshById.set(structure.id, mesh);
    scene.add(mesh);
  }

  const arrows = buildArrows(data.projections, meshById);
  for (const arrow of arrows) scene.add(arrow.group);

  // Name labels (hover + show-all) for structures, plus connection labels on the
  // arrows (shown with "show all"). Mounted as an HTML overlay over the canvas.
  const labels = createLabels(meshes, arrows, document.body);
  window.addEventListener("resize", () => labels.resize());

  // Both hemispheres (plus a midline singleton) sharing a mesh's base: a legend
  // row / double-click / search pick isolates this whole pair, and pinning it
  // names both sides. The id base is the structure id minus its _R/_L suffix.
  const baseOf = (id) => id.replace(/_[LR]$/, "");
  const isolateGroupFor = (mesh) => {
    const base = baseOf(mesh.userData.structure.id);
    return meshes.filter((m) => baseOf(m.userData.structure.id) === base);
  };

  // Picking helpers, shared by mouse hover, click, and touch tap so the raycast
  // logic isn't duplicated. `setPointer` maps screen coords to NDC and aims the
  // ray once; the pick functions then intersect different object sets.
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const canvas = renderer.domElement;
  const setPointer = (clientX, clientY) => {
    pointer.x = (clientX / window.innerWidth) * 2 - 1;
    pointer.y = -(clientY / window.innerHeight) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
  };
  // Nearest *visible* structure intersection under a screen point (the three.js
  // hit record, so callers also get `.distance`), or null. The distance lets the
  // click handler decide whether a structure or an arrow is the front-most thing
  // under the cursor.
  const pickStructureHit = (clientX, clientY) => {
    setPointer(clientX, clientY);
    for (const hit of raycaster.intersectObjects(meshes, false)) {
      if (hit.object.visible) return hit;
    }
    return null;
  };
  // Just the nearest visible structure mesh (hover + double-click only need that).
  const pickAt = (clientX, clientY) => pickStructureHit(clientX, clientY)?.object || null;

  // Connection info panel (populated when an arrow is clicked or a connection is
  // picked in the search). Created here so the click/tap handlers below can use it.
  const tabs = createPanelTabs();
  const info = createInfoPanel(data);
  // Open (or re-activate) a detail tab for the thing a select* just rendered +
  // focused; the reopen thunk re-runs that select* so clicking the tab restores
  // the panel + the 3D focus. Kept here (not in createInfoPanel) so the tab's key
  // and how to re-focus the scene live with the select* layer.
  // Run after any detail tab opens / the last one closes, so the URL hash can be
  // rewritten to mirror the current focus. Assigned once the deep-link layer is set up.
  let afterTabChange = () => {};
  const openDetailTab = (key, title, reopen) => {
    // The single choke point every node focus (drug / receptor / target / structure /
    // connection / circuit / group) passes through, so emit one semantic analytics
    // event here (the `key` is already `<kind>:<id>`) instead of at each call site.
    // No-op unless umami is loaded (see js/app-init.js window.trackEvent).
    window.trackEvent?.("focus", { node: key });
    const r = tabs.openDetail({ key, title, reopen });
    afterTabChange();
    return r;
  };

  // Selection + isolation controller: glowing halo on the structure picked by
  // click / double-click / search, plus the legend-driven isolate/dim mode. Owns
  // the structure + arrow opacity so it composes with the transparency slider.
  const selection = createSelection({ meshes, arrows });
  // Pin the selected structure's floating name: while a structure is the active
  // single selection its label stays on regardless of hover, and hovering another
  // region adds its label rather than replacing the pinned one. Driven off the
  // selection highlight so every path that selects a structure (3D click, search,
  // a related-structure panel row) behaves identically, and any non-structure
  // focus (arrow / target / drug) or a clear drops the pin automatically. The
  // whole L/R base pair is pinned (not just the clicked mesh), so both
  // hemispheres show their name for a paired structure.
  selection.onHighlight((mesh) => labels.setPinned(mesh ? isolateGroupFor(mesh) : null));
  // When the last detail tab is closed, nothing is selected any more: clear the
  // 3D focus (halo / isolate / dim / dots) so the scene matches the empty strip.
  tabs.setOnEmpty(() => { selection.clear(); afterTabChange(); });

  // Circuit "traveling pulse" animation: glowing beads sweeping each isolated
  // circuit's arrows from source to target (js/circuit-anim.js). Started from the
  // circuit legend row (in buildLegend) and stopped here the instant the focus
  // stops being exactly that circuit: every focus change fires this onIsolate
  // hook with the live pinned-arrow set, and matches() is true only while that
  // set is still the animating circuit (a clear, a different circuit, a
  // neurotransmitter focus or a legend isolate all flip it false).
  const circuitAnim = createCircuitAnimation({ scene });
  selection.onIsolate((_isolated, focusedArrows) => {
    if (!circuitAnim.matches(focusedArrows)) circuitAnim.stop();
  });

  // Receptor/target expression markers + focus (js/receptor-markers.js). Clicking a
  // row in the merged "Receptors & targets" section dims the brain to just the
  // regions the receptor/target sits in (via setCircuit, no arrow pin, so the
  // pathways fade too and the dots are the only bright thing) and scatters glowing
  // dots over those regions' surfaces; a ubiquitous receptor lights every region.
  // Clicking the active one clears it. The dots are dropped the moment the focus
  // stops being exactly that structure set (a clear, a circuit, a legend isolate,
  // another receptor/target), watched off the selection state like the circuit
  // pulse. The same path serves receptors and non-receptor targets; only the info
  // view differs (showReceptor vs the lighter showTarget).
  const receptorMarkers = createReceptorMarkers({ scene });
  let activeTargetId = null;
  let reflectTargets = () => {};
  const refreshTargetRows = () => reflectTargets(activeTargetId);
  const targetMeshesOf = (tgt) =>
    tgt.structureIds.map((id) => meshById.get(id)).filter(Boolean);
  const focusTarget = (tgt, { frame = false, preview = false } = {}) => {
    const meshSet = targetMeshesOf(tgt);
    selection.setCircuit(meshSet, []);
    receptorMarkers.show(meshSet, tgt.swatchColor);
    if (preview) return; // hover preview: dim + dots only, no panel/tab/spread
    autoSpreadIfDeep(meshSet);
    if (tgt.kind === "receptor") info.showReceptor(tgt.receptor);
    else info.showTarget(tgt);
    // From the search box, frame the regions (the whole brain for a ubiquitous
    // receptor); from the legend row, leave the view where it is.
    if (frame) focus.focusMeshes(meshSet);
    activeTargetId = tgt.id;
    refreshTargetRows();
    openDetailTab(`target:${tgt.id}`, tgt.name, () => focusTarget(tgt));
  };
  const toggleTarget = (tgt) => {
    if (activeTargetId === tgt.id) selection.clear(); // watcher hides dots
    else focusTarget(tgt);
  };
  // Picking a target in the search box always focuses it (and frames it), never
  // toggles it off, the same way a structure/connection search result behaves.
  const selectTarget = (tgt) => focusTarget(tgt, { frame: true });
  selection.onIsolate((isolated) => {
    if (receptorMarkers.active && !receptorMarkers.matches(isolated)) {
      receptorMarkers.hide();
      activeTargetId = null;
      refreshTargetRows();
    }
  });
  reflectTargets = buildTargetLegend(data, toggleTarget);

  // Per-drug animation + focus (js/drug-anim.js), the same shape as the receptor
  // focus above. Clicking a drug row dims the brain to the union of regions its
  // targets sit in and animates each target's regions coloured by the binding's
  // net effect (boost/block/modulate, the dots + wash). On top of that, the drug's
  // transmitter-system pathways (its `flowKinds`, resolved in js/data.js) are
  // pinned opaque and ride flowing beads via the shared circuit pulse, the
  // "by-mechanism flow" overlay: focusing an SSRI lights the serotonergic fan, an
  // SNRI the noradrenergic + serotonergic ones, etc. A drug whose systems have no
  // modeled ascending pathway pins no arrows, so it falls back to dots + wash only
  // (setCircuit with an empty arrow set, exactly as before). Both the dots and the
  // flow are dropped the moment the focus stops being exactly that drug's region
  // set (a clear, a circuit, a receptor, another drug): the dots via the drugAnim
  // watcher below, the flow via the shared circuitAnim watcher (its pinned-arrow
  // set stops matching).
  const drugAnim = createDrugAnimation({ scene });
  let activeDrugId = null;
  let reflectDrugs = () => {};
  const refreshDrugRows = () => reflectDrugs(activeDrugId);
  const drugMeshesOf = (drug) =>
    drug.structureIds.map((id) => meshById.get(id)).filter(Boolean);
  // The arrows carrying this drug's target transmitter systems (its mapped
  // projection kinds), the set the flow overlay rides. Empty when the drug has no
  // mapped system, so the overlay is simply absent for it.
  const flowArrowsOf = (drug) => {
    const kinds = new Set(drug.flowKinds || []);
    return kinds.size ? arrows.filter((a) => kinds.has(a.projection.kind)) : [];
  };
  const focusDrug = (drug, { frame = false, preview = false } = {}) => {
    const meshSet = drugMeshesOf(drug);
    const flowArrows = flowArrowsOf(drug);
    selection.setCircuit(meshSet, flowArrows);
    drugAnim.show(drug, meshById);
    // Per-kind flow direction/weight (js/data.js flowSystems): the pulse rides
    // "up" the fan when the drug raises that system's tone, damped "down" when it
    // lowers it, its intensity scaled by the drug's affinity on that system.
    circuitAnim.play(flowArrows, drug.flowSystems || {}); // no-op for a drug with no mapped pathways
    if (preview) return; // hover preview: dim + dots + flow only, no panel/tab/spread
    autoSpreadIfDeep(meshSet);
    info.showDrug(drug);
    // From the search box, frame the affected regions; from the list row, leave
    // the view where it is.
    if (frame && meshSet.length) focus.focusMeshes(meshSet);
    activeDrugId = drug.id;
    refreshDrugRows();
    openDetailTab(`drug:${drug.id}`, drug.name, () => focusDrug(drug));
  };
  const toggleDrug = (drug) => {
    if (activeDrugId === drug.id) selection.clear(); // watcher hides the animation
    else focusDrug(drug);
  };
  const selectDrug = (drug) => focusDrug(drug, { frame: true });
  selection.onIsolate((isolated) => {
    if (drugAnim.active && !drugAnim.matches(isolated)) {
      drugAnim.hide();
      activeDrugId = null;
      refreshDrugRows();
    }
  });
  reflectDrugs = buildDrugLegend(data, toggleDrug);

  // Auto-rotate is on by default (a slow turn on load), but the moment the user
  // reaches in to inspect something it should hold still. Stop it (and untick
  // the box so the UI stays truthful) on any content pick routed through the
  // selection controller: a structure/arrow click-tap-or-search, a legend
  // isolate, or a circuit. Clearing the selection does not re-enable it.
  const autorotateBox = document.getElementById("autorotate");
  const stopAutoRotate = () => {
    if (!controls.autoRotate) return;
    controls.autoRotate = false;
    if (autorotateBox) autorotateBox.checked = false;
  };
  selection.onPick(stopAutoRotate);

  // Arrow picking, two object sets for two purposes:
  //  - `arrowPickables` includes each arrow's fat invisible pick hull
  //    (PICK_RADIUS), so a thin arrow over empty space is still easy to
  //    click/tap; used only as the empty-space fallback below.
  //  - `visibleArrowPickables` is the *visible* geometry only (tube + cone(s),
  //    minus that hull), so the click handler can compare an arrow's real
  //    on-screen depth against a structure's and pick whichever is in front.
  // Arrows hidden in isolated screenshot views (group.visible=false) are ignored.
  const arrowPickables = arrows.flatMap((arrow) => arrow.meshes);
  const visibleArrowPickables = arrows.flatMap((a) => a.meshes.filter((m) => m !== a.pick));
  const firstVisibleArrowHit = (pickables) => {
    for (const hit of raycaster.intersectObjects(pickables, false)) {
      const arrow = hit.object.userData.arrow;
      if (arrow && arrow.group.visible) return { arrow, distance: hit.distance };
    }
    return null;
  };
  // Arrow under a point via the generous pick hull (or null).
  const pickArrowAt = (clientX, clientY) => {
    setPointer(clientX, clientY);
    // The fat pick hulls are rebuilt lazily (deferred during a spread), so make
    // sure any stale ones are current before raycasting them.
    for (const a of arrows) a.ensurePickGeometry();
    return firstVisibleArrowHit(arrowPickables)?.arrow || null;
  };
  // Nearest *visible* arrow part under a point ({arrow, distance}) or null.
  const pickVisibleArrowHit = (clientX, clientY) => {
    setPointer(clientX, clientY);
    return firstVisibleArrowHit(visibleArrowPickables);
  };

  // What a tap/click does: select whatever is *visually* front-most under the
  // point. We compare depths so a click on a region selects the region even when
  // an arrow's fat (invisible) pick hull happens to pass over it; an arrow wins
  // only when its *visible* tube/cone is at least as near the camera as the
  // nearest structure. With nothing solid under the point (empty space) we fall
  // back to the generous arrow hull, so a thin arrow over the background is still
  // easy to hit; a true miss clears the halo, label, and panel. handleSelect owns
  // the label set so callers need no separate fallback.
  const handleSelect = (clientX, clientY) => {
    const structHit = pickStructureHit(clientX, clientY);
    const arrowHit = pickVisibleArrowHit(clientX, clientY);
    let arrow = null;
    if (arrowHit && (!structHit || arrowHit.distance <= structHit.distance)) {
      arrow = arrowHit.arrow; // a visible arrow is at/in front of the structure
    } else if (!structHit) {
      // Nothing visible under the point: let the fat pick hull catch a thin arrow.
      arrow = pickArrowAt(clientX, clientY);
    }
    if (arrow) {
      selectConnection(arrow); // plain click: no camera move
      return true;
    }
    const mesh = structHit ? structHit.object : null;
    if (mesh) {
      // A structure opens its own panel (name, group, connections).
      selectStructure(mesh);
    } else {
      // A true miss on empty space clears the halo + label and deselects to the
      // Settings tab (the opened detail tabs stay in the strip as history).
      selection.select(null);
      labels.setHovered(null);
      tabs.showSettings();
    }
    return true;
  };

  // Hover picking. When a focus is active (a halo'd structure, an isolated set,
  // a circuit, a receptor's regions, ...), a focused region the ray passes
  // through wins even when a non-focused region sits nearer the camera, so the
  // thing you focused always names *itself* on hover rather than whatever happens
  // to occlude it (e.g. an isolated deep nucleus hidden behind the dimmed
  // cortex). With nothing focused this is just the nearest visible structure.
  const pickHover = (clientX, clientY) => {
    setPointer(clientX, clientY);
    const hits = raycaster.intersectObjects(meshes, false);
    const focus = selection.getSelected();
    if (focus && focus.meshes.size) {
      for (const hit of hits) {
        if (hit.object.visible && focus.meshes.has(hit.object)) return hit.object;
      }
    }
    for (const hit of hits) if (hit.object.visible) return hit.object;
    return null;
  };

  // Mouse: hover a region to reveal its name. Mouse-only so that touch-drag
  // rotation doesn't flicker labels (touch uses tap, below).
  canvas.addEventListener("pointermove", (event) => {
    if (event.pointerType !== "mouse") return;
    labels.setHovered(pickHover(event.clientX, event.clientY));
  });
  canvas.addEventListener("pointerleave", (event) => {
    if (event.pointerType === "mouse") labels.setHovered(null);
  });

  // Mouse click (a press + release that didn't drag) selects: an arrow opens its
  // info panel, a miss closes it. Thresholds on movement/time so dragging to
  // rotate (OrbitControls) is never mistaken for a click.
  let mouseDown = null;
  canvas.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse") {
      mouseDown = { x: event.clientX, y: event.clientY, t: performance.now() };
    }
  });
  canvas.addEventListener("pointerup", (event) => {
    if (event.pointerType !== "mouse" || !mouseDown) return;
    const moved = Math.hypot(event.clientX - mouseDown.x, event.clientY - mouseDown.y);
    const elapsed = performance.now() - mouseDown.t;
    mouseDown = null;
    if (moved < 6 && elapsed < 500) handleSelect(event.clientX, event.clientY);
  });

  // Touch: a tap on a structure reveals its name; a tap on empty space clears
  // it. A tap is a single finger pressed and released with little movement, so
  // it never competes with one-finger rotate or two-finger pan/zoom (those move
  // too far, or involve a second finger, and are ignored here).
  let tapStart = null;
  let touchPointers = 0;
  let gestureMultiTouch = false;
  canvas.addEventListener("pointerdown", (event) => {
    if (event.pointerType !== "touch") return;
    touchPointers += 1;
    if (touchPointers > 1) {
      // A second finger means this is a pan/zoom gesture, not a tap.
      gestureMultiTouch = true;
      tapStart = null;
      return;
    }
    gestureMultiTouch = false;
    tapStart = { x: event.clientX, y: event.clientY, t: performance.now() };
  });
  canvas.addEventListener("pointerup", (event) => {
    if (event.pointerType !== "touch") return;
    touchPointers = Math.max(0, touchPointers - 1);
    const start = tapStart;
    const wasMultiTouch = gestureMultiTouch;
    if (touchPointers === 0) {
      gestureMultiTouch = false;
      tapStart = null;
    }
    if (wasMultiTouch || !start) return;
    const moved = Math.hypot(event.clientX - start.x, event.clientY - start.y);
    const elapsed = performance.now() - start.t;
    if (moved < 12 && elapsed < 400) {
      // An arrow tap opens its info panel; otherwise the structure under the tap
      // is haloed + named (and a tap on empty space clears everything).
      // handleSelect owns all of that, so there is no separate fallback.
      handleSelect(event.clientX, event.clientY);
    }
  });
  canvas.addEventListener("pointercancel", (event) => {
    if (event.pointerType !== "touch") return;
    touchPointers = Math.max(0, touchPointers - 1);
    if (touchPointers === 0) {
      gestureMultiTouch = false;
      tapStart = null;
    }
  });

  // Double-click to focus: on a structure, isolate it (both hemispheres) exactly
  // like clicking its legend row; on empty space, recenter the whole brain (same
  // as the reset button). The move is a smooth tween advanced in the render loop;
  // grabbing the controls cancels it so a drag always wins.
  const focus = createCameraFocus({
    camera, controls, meshes,
    // The live focused mesh set (a legend/search isolate, a circuit/group pin, a
    // receptor/drug region set, or a single halo), so a spread keeps whatever is
    // focused centered; null when nothing is focused (the pivot-follow stays off).
    getFocusMeshes: () => {
      const sel = selection.getSelected();
      return sel ? [...sel.meshes] : null;
    },
  });
  controls.addEventListener("start", () => focus.cancel());

  // "See inside" mode: hide the near hemisphere so the deep nuclei show through.
  const cull = createNearCull({ meshes, camera, controls });

  // Every way of picking content (click/tap, double-click, search, a
  // structure-panel connection row) funnels through these two helpers, so the
  // "halo it + label/panel it + maybe frame the camera" sequence lives in one
  // place instead of being copy-pasted at each entry point. `frame` moves the
  // camera (search / double-click); a plain click leaves the view where it is.
  // `isolate` dims the rest of the brain down to the picked thing. The uniform
  // rule across the app: a pick from SEARCH or a DETAIL PANEL row always focuses
  // (frame:true, isolate:true), so structures, connections, targets and drugs all
  // behave the same (target/drug focus is the equivalent setCircuit in focusTarget
  // / focusDrug). Only a plain 3D click stays halo-only (isolate:false), with
  // double-click to isolate.
  const selectStructure = (mesh, { frame = false, isolate = false, preview = false } = {}) => {
    if (frame && !preview) focus.focusStructure(mesh);
    // A search result or a detail-panel jump (e.g. a "Found in" region row) picks a
    // structure the way a legend row does: isolate its hemisphere pair so the rest
    // of the brain dims (setCircuit with no pinned arrows is exactly the dimming a
    // legend-row toggleIsolate produces). A plain 3D click and the legend's own
    // onPickStructure pass isolate:false: the 3D click stays halo-only (double-click
    // isolates), and the legend has already toggled the isolate set itself (kept
    // additive there). The tab's reopen thunk preserves `isolate` so re-activating a
    // search/detail tab restores the dim, not just the halo.
    if (isolate) {
      const group = isolateGroupFor(mesh);
      selection.setCircuit(group, []);
      if (!preview) autoSpreadIfDeep(group); // a deep nucleus: blow the brain apart
    }
    // select() drives selection.onHighlight, which pins this structure's label on
    // (so the name stays put after the pointer leaves, and survives hovering other
    // regions), so no explicit setHovered is needed here.
    selection.select(mesh);
    if (preview) return; // hover preview: apply the scene focus only, no panel/tab
    const structure = mesh.userData.structure;
    info.showStructure(structure);
    openDetailTab(`structure:${structure.id}`, structure.base_name || structure.name,
      () => selectStructure(mesh, { isolate }));
  };
  // A projection has no id field, but a from->to pair is unique per pathway (the
  // hemispheres differ), so it keys the tab. The reopen re-halos the arrow when
  // one was built; a pathway with no drawn arrow just re-renders the panel.
  const connectionKey = (proj) => `connection:${proj.from}->${proj.to}`;
  const selectConnection = (arrow, { frame = false, isolate = false, preview = false, siblings = [] } = {}) => {
    if (frame && !preview) focus.focusConnection(arrow);
    // A search result or a detail-panel connection row puts the pathway "fully in
    // focus" like every other search pick: pin the arrow + its two endpoints opaque
    // and dim the rest of the brain (setCircuit), the same focus a projection-group
    // / circuit row gives. A plain 3D arrow click passes isolate:false and stays
    // halo-only (consistent with the plain structure click). The reopen thunk keeps
    // `isolate` so re-activating the tab restores the dim. `siblings` are the
    // opposite-hemisphere twin arrow(s): a search pick collapses L/R twins into one
    // row and pins both sides, so "corticothalamic" lights both, not just the right.
    if (isolate && arrow.fromMesh && arrow.toMesh) {
      const ends = [arrow.fromMesh, arrow.toMesh];
      const pins = [arrow];
      for (const sib of siblings) {
        if (sib.fromMesh) ends.push(sib.fromMesh);
        if (sib.toMesh) ends.push(sib.toMesh);
        pins.push(sib);
      }
      selection.setCircuit(ends, pins);
      if (!preview) autoSpreadIfDeep(ends);
    }
    selection.selectArrow(arrow); // halo the arrow on top of the focus
    if (preview) return; // hover preview: scene focus only, no panel/tab
    const proj = arrow.projection;
    info.show(proj);
    openDetailTab(connectionKey(proj), proj.label || t("info.connection"),
      () => selectConnection(arrow, { isolate, siblings }));
  };

  // Clicking a connection row inside a structure panel jumps to that pathway
  // (frames + isolates it, halos the arrow, swaps in the connection panel) just
  // like picking the connection in search.
  info.onConnection((proj) => {
    const arrow = arrows.find((a) => a.projection === proj);
    if (arrow) { selectConnection(arrow, { frame: true, isolate: true }); return; }
    info.show(proj); // no arrow built for this pathway: details only
    openDetailTab(connectionKey(proj), proj.label || t("info.connection"),
      () => info.show(proj));
  });

  // Clicking a target (binding) row inside a drug panel focuses that target,
  // framing its regions + lighting its dots + opening its panel, just like
  // picking the target in the "Receptors & targets" legend or in search.
  info.onTarget(selectTarget);

  // Clicking a region in a receptor / target panel's "Found in" list jumps to
  // that structure (frames it + halos it + opens its tab), like a structure
  // search pick. A base resolves to its midline mesh, else its _R then _L
  // hemisphere (the receptor footprint spans both; we centre one).
  info.onStructure((base) => {
    const id = [base, `${base}_R`, `${base}_L`].find((sid) => meshById.has(sid));
    const mesh = id && meshById.get(id);
    if (mesh) selectStructure(mesh, { frame: true, isolate: true });
  });

  // Clicking a drug in a receptor / target panel's "Interacting drugs" list focuses
  // that drug (dim + animation + drug panel + tab), exactly like a Drugs legend row
  // / drug search pick, so you can go from a target to every drug acting on it.
  info.onDrug(selectDrug);

  // Clicking a "Projections affected" row in a drug panel focuses that projection
  // group (isolates its arrows + opens its tab), exactly like its Projections legend
  // row, so you can go from a drug to the pathway system it engages.
  info.onProjectionGroup((group) => focusProjectionGroup(group, { frame: true }));

  canvas.addEventListener("dblclick", (event) => {
    const mesh = pickAt(event.clientX, event.clientY);
    if (mesh) {
      // Same as clicking the structure's legend row: isolate/focus the pair.
      selection.toggleIsolate(isolateGroupFor(mesh));
    } else {
      // Double-click on empty space is a full reset, same as the reset button.
      focus.recenter();
      selection.clear();
    }
  });

  const projVis = createProjectionVisibility(arrows, labels);

  // Arrow colour mode + legend. The legend's focus-greying callback is registered
  // once here; rebuildLegend just swaps which function it delegates to, so the
  // colour toggle (which rebuilds the legend so its Projections rows match the new
  // arrow colours) never stacks onIsolate listeners.
  let signColorMode = false; // false = per-transmitter (default), true = excit/inhib
  let reflectLegend = () => {};
  selection.onIsolate((isolated, focusedArrows) => reflectLegend(isolated, focusedArrows));
  const applyArrowColors = () => {
    for (const a of arrows) {
      a.setColor(signColorMode ? a.projection.signColor : a.projection.color);
    }
  };
  // Circuit + projection-group focus, the same shape as focusDrug/focusTarget: a
  // legend row click (toggle handled in buildLegend off its reflect-derived active
  // state) delegates the *isolate + panel + tab* to these, and the tab's reopen
  // thunk re-runs the same function. A circuit plays the traveling pulse (the
  // circuitAnim watcher stops it on the next focus change); a projection group is
  // a static pinned-arrow focus (no pulse), matching the prior behaviour. Both
  // recompute their meshes/arrows from the data so the reopen thunk is durable.
  const circuitMeshesOf = (circuit) =>
    circuit.structures.map((id) => meshById.get(id)).filter(Boolean);
  const arrowsAmong = (meshSet) =>
    arrows.filter((a) => meshSet.has(a.fromMesh) && meshSet.has(a.toMesh));
  const focusCircuit = (circuit, { frame = false, preview = false } = {}) => {
    const cMeshes = circuitMeshesOf(circuit);
    const cArrows = arrowsAmong(new Set(cMeshes));
    selection.setCircuit(cMeshes, cArrows);
    circuitAnim.play(cArrows);
    if (preview) return; // hover preview: dim + pulse only, no panel/tab/spread
    autoSpreadIfDeep(cMeshes);
    info.showCircuit(circuit);
    if (frame && cMeshes.length) focus.focusMeshes(cMeshes);
    openDetailTab(`circuit:${circuit.id}`, circuit.name, () => focusCircuit(circuit));
  };
  // The (established) arrows this projection group stands for: by sign in sign
  // mode, by kind otherwise (the data record is per kind/sign). Tentative arrows
  // are excluded, matching the established-only legend rows.
  const groupArrowsOf = (group) => arrows.filter((a) =>
    !a.tentative
    && (group.mode === "sign" ? a.projection.sign === group.key
                              : a.projection.kind === group.key));
  const focusProjectionGroup = (group, { frame = false, preview = false } = {}) => {
    const gArrows = groupArrowsOf(group);
    const gMeshes = [...new Set(gArrows.flatMap((a) => [a.fromMesh, a.toMesh]))];
    selection.setCircuit(gMeshes, gArrows); // pin the arrows, no pulse
    if (preview) return; // hover preview: dim only, no panel/tab/spread
    autoSpreadIfDeep(gMeshes);
    info.showProjectionGroup(group);
    if (frame && gMeshes.length) focus.focusMeshes(gMeshes);
    openDetailTab(`group:${group.id}`, group.name, () => focusProjectionGroup(group));
  };

  const rebuildLegend = () => {
    reflectLegend = buildLegend(
      data, meshById, arrows, selection, projVis, circuitAnim, signColorMode,
      // Opening the picked structure's tab (no reframe: keep the legend pick's
      // current camera, just add the detail tab + halo, like the isolate already
      // does in the viewer).
      (mesh) => selectStructure(mesh),
      // Circuit / projection-group row picks: isolate + open the sourced detail
      // panel + tab, exactly like a drug / target row.
      focusCircuit, focusProjectionGroup);
    selection.refresh(); // re-grey the fresh rows for the current isolate state
  };
  rebuildLegend();
  // The static colour key (Legend section) is built once: it shows the scene's
  // encodings (gem-dot signs, drug effect colours, dotted = speculative) from the
  // meta maps and doesn't depend on the arrow colour mode.
  buildLegendKey(data);
  // Fill the About panel's "Sources & provenance" block (grade key + the
  // programmatic coverage tally) from the dataset's meta.
  buildAboutSourcing(data.meta);
  // Arrow colour-mode switch (Neurotransmitter | Potential): a two-state
  // segmented control in the Controls section. Picking an option recolours the
  // arrows and rebuilds the Projections legend rows to match. The switch lives
  // outside #projections-body, so buildLegend's rebuilds never touch it and these
  // listeners persist for the life of the page.
  const colorModeSwitch = document.getElementById("color-mode");
  const modeButtons = colorModeSwitch.querySelectorAll(".mode-btn");
  const setColorMode = (sign) => {
    if (sign === signColorMode) return;
    signColorMode = sign;
    for (const b of modeButtons) {
      const on = (b.dataset.mode === "sign") === sign;
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", String(on));
    }
    applyArrowColors();
    rebuildLegend();
  };
  for (const b of modeButtons) {
    b.addEventListener("click", () => setColorMode(b.dataset.mode === "sign"));
  }

  const { autoSpread, autoSpreadIfDeep, arrowRetrim } = wireControls(
    { controls, meshes, arrows, labels, focus, selection, projVis, cull });
  // Hold arrows a constant apparent width as the camera zooms (advanced by its
  // tick() in the render loop, like arrowRetrim).
  const arrowWidth = createArrowWidth({ arrows, camera, controls, focus });
  const toolbar = wireToolbar({ focus, meshes, arrows, data, selection, tabs, selectStructure, selectConnection, focusTarget, focusDrug, focusCircuit, focusProjectionGroup });
  // A drug panel's clickable Class / Nomenclature opens search with a structured
  // filter (class:"..." / nbn:"...") so you can pivot to the whole class.
  info.onSearch(toolbar.openSearchWithQuery);
  // Clicking a structure illustration / molecule diagram in a panel enlarges it.
  const lightbox = wireImageLightbox();
  info.onImage((src, alt, opts) => lightbox.open(src, alt, opts));
  const shortcutsHelp = wireShortcutsHelp(); // the "?" / keyboard-button popup
  // sourcingModal was created early (the startup gate, above); the Legend + About
  // popups link to it via their "Sources & provenance" rows.
  const legendModal = wireLegendModal(sourcingModal); // toolbar legend button / k key
  const aboutModal = wireAboutModal(sourcingModal); // the toolbar info-button popup
  wireShortcuts(shortcutsHelp, tabs, selection, lightbox, aboutModal, legendModal, sourcingModal); // single-key shortcuts (n/s/l/p/k/c/r/m/f/?/Esc) + Tab cycles detail tabs
  projVis.apply(); // established arrows visible, tentative ones start hidden
  // Honor screenshot/deep-link view params (?only=, ?view=, ?explode=, ...).
  applyViewParams({ scene, camera, controls, meshes, arrows, labels });
  // Scene is built: fill + fade out the loading overlay, revealing the brain just
  // as the assemble intro (created below) begins.
  loading.setProgress(1, t("loading.building"));
  loading.done();
  console.log(
    `Loaded ${meshes.length} structures and ${arrows.length} projections.`,
  );

  // Auto-play the "assemble" intro on a plain load. Grabbing the explode slider
  // cancels it so a manual drag wins. Skipped when ?explode= is pinned (deep
  // links / headless screenshots) so the requested static amount is honored.
  const explodeSlider = document.getElementById("explode");
  const intro = createIntroAnimation(
    { meshes, arrows, slider: explodeSlider, camera, controls, focus });
  explodeSlider.addEventListener("input", () => intro.cancel());
  if (!new URLSearchParams(window.location.search).has("explode")) {
    // Seat the resting pose on the exact framing the reset button produces, so a
    // fresh load already appears centered (not a hardcoded distance that only
    // roughly matched). Done first, so the DEV-banner nudge + intro capture build
    // on the centered pose.
    focus.frameAllNow();
    // When the dev / WIP banner is up (DEV=1 container; same flag dev-banner.js
    // reads), present the brain a little lower + further back so it sits clear
    // below the banner. Done before intro.start() so the captured resting pose
    // (what the intro settles on) already includes it.
    if ((window.__APP_CONFIG__ || {}).dev === "1") {
      camera.position.multiplyScalar(DEV_BANNER_UNZOOM);
      controls.target.y += DEV_BANNER_DROP;
      controls.update();
    }
    // The assemble intro is a decorative animation, so honor the Animations toggle:
    // when off, present the brain already whole (explode 0) instead of playing it in.
    if (animSettings.enabled) intro.start();
    else applyExplode(meshes, 0, arrows);
  }

  // ---- Deep links (URL hash <-> focus) ------------------------------------------
  // A URL hash like `#focusDrug=vortioxetine` / `#focusReceptor=5-HT2A` opens the
  // node's detail tab and focuses it on load (and on hashchange), exactly as picking
  // it from search would. The inverse also holds: focusing any node rewrites the hash
  // to its deep link (see syncHashToFocus), so the address bar is always shareable.
  const linkFold = (s) => foldText(String(s == null ? "" : s));
  const stripSideId = (id) => String(id).replace(/_[LR]$/, "");
  const findByIdOrName = (list, v) => {
    const q = linkFold(v);
    return list.find((o) => linkFold(o.id) === q)
        || list.find((o) => linkFold(o.name) === q);
  };
  // param (lowercased) -> resolver(value) -> true iff it matched & focused a node.
  const deepLinkResolvers = {
    focusdrug: (v) => { const d = findByIdOrName(data.drugs, v); if (d) focusDrug(d, { frame: true }); return !!d; },
    focustarget: (v) => { const tg = findByIdOrName(data.targets, v); if (tg) focusTarget(tg, { frame: true }); return !!tg; },
    focusreceptor: (v) => deepLinkResolvers.focustarget(v), // receptors live in data.targets
    focuscircuit: (v) => { const c = findByIdOrName(data.circuits, v); if (c) focusCircuit(c, { frame: true }); return !!c; },
    focusgroup: (v) => { const g = findByIdOrName(data.projectionGroups, v); if (g) focusProjectionGroup(g, { frame: true }); return !!g; },
    focusstructure: (v) => {
      const q = linkFold(stripSideId(v));
      const group = meshes.filter((m) => {
        const s = m.userData.structure;
        return linkFold(stripSideId(s.id)) === q || linkFold(s.base_name) === q || linkFold(s.name) === q;
      });
      if (!group.length) return false;
      const rep = group.find((m) => !/_[LR]$/.test(m.userData.structure.id)) || group[0];
      selectStructure(rep, { frame: true, isolate: true });
      return true;
    },
    focusconnection: (v) => {
      const q = linkFold(v);
      const byBase = new Map();
      for (const a of arrows) {
        const p = a.projection;
        const key = `${stripSideId(p.from)}->${stripSideId(p.to)}`;
        (byBase.get(key) || byBase.set(key, []).get(key)).push(a);
      }
      for (const [key, arr] of byBase) {
        if (linkFold(key) === q || linkFold(arr[0].projection.label) === q) {
          selectConnection(arr[0], { frame: true, isolate: true, siblings: arr.slice(1) });
          return true;
        }
      }
      return false;
    },
  };
  const applyDeepLink = () => {
    const raw = window.location.hash.replace(/^#/, "");
    if (!raw) return false;
    for (const [k, val] of new URLSearchParams(raw)) {
      const fn = deepLinkResolvers[k.toLowerCase()];
      if (fn && val && fn(val)) return true;
    }
    return false;
  };

  // The inverse: build the shareable link for the active detail tab (`<kind>:<id>`).
  const KIND_TO_PARAM = {
    drug: "focusDrug", target: "focusTarget", structure: "focusStructure",
    connection: "focusConnection", circuit: "focusCircuit", group: "focusGroup",
  };
  const currentDeepLink = () => {
    const key = tabs.activeKey();
    const idx = key ? key.indexOf(":") : -1;
    if (idx < 0) return null;
    const param = KIND_TO_PARAM[key.slice(0, idx)];
    if (!param) return null;
    const id = key.slice(idx + 1);
    const value = param === "focusStructure" ? stripSideId(id) : id;
    const url = new URL(window.location.href);
    url.hash = `${param}=${encodeURIComponent(value)}`;
    return url.toString();
  };

  // Keep the address bar in sync with the focus, so the URL is always the shareable
  // deep link for whatever is on screen: copying it is just selecting the URL bar, no
  // dedicated button. `history.replaceState` updates the URL WITHOUT firing
  // `hashchange` (so it never loops back into applyDeepLink) and without spamming
  // back/forward history with every focus. Clearing the focus strips the hash.
  const focusHash = () => {
    const link = currentDeepLink();
    return link ? new URL(link).hash : "";
  };
  const syncHashToFocus = () => {
    const want = focusHash();
    if (want !== window.location.hash) {
      history.replaceState(null, "",
        want || window.location.pathname + window.location.search);
    }
  };
  afterTabChange = syncHashToFocus;

  // Apply an initial deep link (after the intro exists, so a focused node cancels the
  // assemble intro rather than fighting its explode tween), then react to later
  // hash changes (manual edits / pasted links / back-forward). Our own focus-driven
  // updates use replaceState above, which does not fire this event.
  if (applyDeepLink()) intro.cancel();
  window.addEventListener("hashchange", applyDeepLink);

  // On-demand rendering: a mostly-static brain has no reason to repaint at 60fps,
  // which only burns battery / spins fans / throttles phones. We render a frame
  // only when something actually changed: an animation is running (each tick()
  // below reports whether it is active), the controls moved (OrbitControls.update
  // returns true while damping settles or auto-rotate spins), or `invalidate()`
  // was called. `invalidate` is wired to every user input below as a catch-all so
  // no interaction is ever missed, and the controls' own `change` event covers
  // every camera move (drag / wheel / pinch / programmatic). When truly idle (no
  // input, no animation) the loop calls only the cheap tick/update checks and
  // skips the render + CSS2D passes entirely, holding the last drawn frame.
  let needsRender = true;
  const invalidate = () => { needsRender = true; };
  controls.addEventListener("change", invalidate);
  window.addEventListener("resize", invalidate);

  // Adaptive rendering (Task): lower the pixel ratio + animation detail when frames
  // drop, raise it back when they recover. Fed once per frame below with whether an
  // animated render actually happened.
  const adaptive = createAdaptiveQuality({ renderer, baseDpr });

  // Toggling the Animations checkbox flips animSettings; react to it here (where the
  // decorative controllers live): repaint once so a static frame draws, and when
  // turning OFF, halt the circuit traveling pulse (its beads persist otherwise; the
  // gem/wash controllers freeze themselves in their own tick()s). Turning back ON
  // resumes motion on the next focus.
  animSettings.subscribe(() => {
    if (!animSettings.enabled) circuitAnim.stop();
    invalidate();
  });
  // Belt-and-suspenders: any user input repaints, so adding a new control never
  // needs to remember to call invalidate. Capture phase + passive so this only
  // observes (it never preventDefaults, leaving the real handlers untouched).
  for (const ev of ["pointerdown", "pointermove", "pointerup", "wheel",
                    "keydown", "input", "change", "click"]) {
    window.addEventListener(ev, invalidate, { capture: true, passive: true });
  }

  renderer.setAnimationLoop(() => {
    // Advance the intro + any focus/recenter tween before controls.update()
    // reads the target + camera position for this frame. Each tick() returns
    // whether it animated this frame; controls.update() returns whether the
    // camera moved (damping / auto-rotate). Any true keeps us rendering.
    let active = false;
    if (intro.tick()) active = true;
    if (autoSpread.tick()) active = true;
    if (arrowRetrim.tick()) active = true;
    if (focus.tick()) active = true;
    if (circuitAnim.tick()) active = true;
    if (receptorMarkers.tick()) active = true;
    if (drugAnim.tick()) active = true;
    if (controls.update()) active = true;
    // After controls.update() so it reads this frame's settled camera distance.
    if (arrowWidth.tick()) active = true;
    if (active) needsRender = true;
    const rendered = needsRender;
    // Adaptive quality watches the frame time of actually-rendered animated frames
    // and may step the pixel ratio down/up; a level change forces one more repaint.
    if (adaptive.tick(rendered && active)) needsRender = true;
    if (!needsRender) return; // idle: skip the render + label passes this frame
    needsRender = false;
    // After controls.update() so the cull reads this frame's camera + target.
    cull.tick();
    renderer.render(scene, camera);
    // CSS2D labels render as a separate DOM pass after the WebGL frame.
    labels.render(scene, camera);
  });
}

main();
