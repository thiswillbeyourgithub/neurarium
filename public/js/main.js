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
import { buildArrows } from "./arrows.js";
import { createLabels } from "./labels.js";
import { createCircuitAnimation } from "./circuit-anim.js";
import { createReceptorMarkers } from "./receptor-markers.js";
import { createDrugAnimation } from "./drug-anim.js";
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

// Fold a string for accent- + case-insensitive matching: lowercase, then strip
// combining diacritical marks (NFD decomposes e.g. "é" -> "e" + U+0301, "ç" ->
// "c" + U+0327, which we then drop). So the search/filter find "sérotonine" when
// the user types "seroto", and ignore case. Used by the toolbar search + the drug
// filter so both behave the same.
function foldText(s) {
  return String(s)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
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

// Small status pill, used only for the brief "Loading brain data..." message;
// failures surface as red error banners (js/error-banner.js), not here.
function setStatus(message) {
  const el = document.getElementById("status");
  if (!el) return;
  el.textContent = message;
  el.style.display = message ? "block" : "none";
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
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
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

  return { scene, camera, renderer, controls };
}

/**
 * Position every region for a given explode amount, pushing each radially
 * outward from the brain center along its stored direction.
 * @param {THREE.Mesh[]} meshes
 * @param {number} amount  Slider value in [0, 1].
 * @param {import("./arrows.js").ProjectionArrow[]} arrows
 */
function applyExplode(meshes, amount, arrows) {
  for (const mesh of meshes) {
    const { base, dir } = mesh.userData;
    const distance = base.length() * amount * EXPLODE_STRENGTH;
    mesh.position.copy(base).addScaledVector(dir, distance);
  }
  // Arrows follow the moved centers.
  for (const arrow of arrows) arrow.update();
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
  // always-visible toggle headers (in index.html) are left untouched. The action
  // buttons live in an actions container authored in the HTML per section (the
  // "Show all names" button in #structures-actions; "Hide projections" + the
  // colour-mode switch in #projections-actions); keep that exact node (it carries
  // the wireControls click handlers) as the sole survivor and append the generated
  // rows after it, so the buttons stay first. The structure rows go to the
  // Structures section; the projection / circuit / hypothetical rows to the
  // Projections section. One shared `reflect` (returned below) greys rows across
  // both, so the focus-state logic is not duplicated.
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
    cap.textContent = t(captionKey);
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
    /** Set the callback run when the last detail tab is closed (clears the 3D). */
    setOnEmpty(fn) { onEmpty = fn; },
  };
}

/**
 * Build the detail panel renderer. Each show*() method renders a connection /
 * structure / receptor / target / drug into the Details pane's #info-body. It is
 * pure rendering: opening the matching tab + applying the 3D focus is the caller's
 * job (the select* layer in main(), which calls openDetailTab), so this is reused
 * unchanged whether a detail is first picked or re-shown by clicking its tab.
 * @param {import("./data.js").BrainData} data
 */
function createInfoPanel(data) {
  const body = document.getElementById("info-body");
  const nameOf = (id) => data.byId.get(id)?.name || id;

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
  // Set by the caller (onSearch): run a search query. A drug panel's clickable
  // Class / Nomenclature values hand back a `field:"value"` query string; the caller
  // opens the search box pre-filled with it (see wireToolbar.openSearchWithQuery).
  let onSearchPick = () => {};
  // Resolve a drug binding's `target` key to its merged-list entry, so a binding
  // row can focus that target (a receptor entry shares its id; a non-receptor one
  // its drug_targets key). Only focusable entries become clickable.
  const targetById = new Map(data.targets.map((tg) => [tg.id, tg]));

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
  const baseResolves = (base) =>
    data.byId.has(base) || data.byId.has(`${base}_R`) || data.byId.has(`${base}_L`);

  // The "Found in" region list shared by showReceptor / showTarget: one <li> per
  // location, parallel arrays of display names + their base ids. A row whose base
  // resolves to a structure becomes clickable and jumps there via onStructurePick;
  // an unresolved one stays plain text.
  const locationList = (names, bases) => {
    const ul = el("ul");
    names.forEach((name, i) => {
      const base = bases && bases[i];
      const li = el("li", null, name);
      if (base && baseResolves(base)) {
        li.classList.add("clickable");
        li.addEventListener("click", () => onStructurePick(base));
      }
      ul.appendChild(li);
    });
    return ul;
  };

  // The nearest ancestor that establishes a containing block for a position:fixed
  // descendant (a transform / filter / backdrop-filter / perspective / will-change
  // / paint-contain), or null if none (then fixed is viewport-relative). The panel
  // #controls carries a backdrop-filter, so our fixed tooltip is offset by it; we
  // walk this generically rather than hardcoding #controls.
  const fixedContainingBlock = (node) => {
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
  };

  // Only one tooltip is pinned at a time: opening one closes whichever was open,
  // so tapping a second source pill dismisses the first instead of stacking popups.
  // Holds the open tip's `hide` (so its scroll/resize listeners are torn down too,
  // not just its `.show` class). Shared across every withTip instance in the panel.
  let openTip = null;

  // Wrap a trigger element with a hover/tap tooltip. The bubble is positioned in
  // viewport coordinates (position: fixed) just above the trigger and clamped to
  // the viewport, so an inline pill (a binding / NbN / description pill) anchors to
  // its own pill exactly like a source-list pill, instead of to a tall positioned
  // ancestor (the whole panel) far from the pill, which left the tooltip stranded
  // near the panel top on touch (it then read as "no tooltip"). Shows on
  // hover/focus (desktop) and is pinned on click/tap (touch, where `:hover` never
  // fires) via the `.show` class. Wraps the per-source provenance pills.
  const withTip = (trigger, tipText) => {
    const wrap = el("span", "help-icon");
    const tip = el("span", "help-tip", tipText);
    tip.setAttribute("role", "tooltip");
    // The bubble is NOT nested under the trigger: while shown it is appended to
    // <body>, so (a) a dimmed/greyed ancestor row (a speculative binding sits at
    // reduced opacity) can't bleed that opacity into the bubble, which would make it
    // unreadable, and the panel's overflow can't clip it, and (b) you can move the
    // pointer onto the bubble itself to read or select its text without it hiding.
    wrap.append(trigger);
    let pinned = false; // a click pins it open (stays put so its text is selectable)
    let hideTimer = 0;
    const place = () => {
      const r = trigger.getBoundingClientRect();
      const tw = tip.offsetWidth, th = tip.offsetHeight, m = 6;
      let left = r.left + r.width / 2 - tw / 2;
      left = Math.max(m, Math.min(left, window.innerWidth - tw - m));
      let top = r.top - th - 4;
      if (top < m) top = r.bottom + 4; // flip below the trigger if no room above
      // `left`/`top` are viewport coordinates. With the bubble in <body> there is
      // normally no fixed-positioning containing block (offsets zero), but keep the
      // generic subtraction in case a transformed/filtered ancestor ever forms one.
      const cb = fixedContainingBlock(tip);
      const cbRect = cb ? cb.getBoundingClientRect() : null;
      const ox = cb ? cbRect.left - cb.scrollLeft : 0;
      const oy = cb ? cbRect.top - cb.scrollTop : 0;
      tip.style.left = `${Math.round(left - ox)}px`;
      tip.style.top = `${Math.round(top - oy)}px`;
    };
    // Keep the fixed bubble glued to its trigger while shown; tear it down if the
    // panel re-renders the trigger out from under us.
    const reposition = () => {
      if (!trigger.isConnected) { close(); return; }
      if (tip.classList.contains("show")) place();
    };
    // A pointer press anywhere outside the badge and the bubble closes a pinned tip
    // (so clicking away dismisses it); presses on either are ignored, so a click into
    // the bubble to select text never closes it.
    const onDocPointer = (e) => {
      if (wrap.contains(e.target) || tip.contains(e.target)) return;
      close();
    };
    const open = () => {
      clearTimeout(hideTimer);
      if (openTip && openTip !== close) openTip(); // close any other open tip
      openTip = close;
      if (!tip.isConnected) document.body.appendChild(tip);
      tip.classList.add("show");
      place();
      // Re-place after this frame: tapping a button can focus-scroll it into view
      // *after* the click handler runs, which would otherwise strand the bubble.
      requestAnimationFrame(place);
      window.addEventListener("scroll", reposition, true);
      window.addEventListener("resize", reposition);
      document.addEventListener("pointerdown", onDocPointer, true);
    };
    const close = () => {
      clearTimeout(hideTimer);
      pinned = false;
      if (openTip === close) openTip = null;
      tip.classList.remove("show");
      tip.remove();
      window.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
      document.removeEventListener("pointerdown", onDocPointer, true);
    };
    // Hover-out closes shortly, unless it was pinned by a click or the pointer is now
    // over the badge or the bubble (so you can cross the small gap between them, and
    // rest on the bubble to read / select it without it vanishing).
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
    // Hover/focus reveal is for pointer + keyboard devices only. On a touch screen a
    // single tap synthesizes mouseenter + focus (both open()) and *then* click (which
    // toggles), so attaching those here would show-then-hide on the first tap and
    // force a second tap. Gating them behind `(hover: hover)` leaves the click-toggle
    // as the sole path on touch, so one tap shows it (tap again to dismiss). On a
    // pointer device a click instead *pins* it (so it stays put to select its text).
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
    return wrap;
  };

  // Per-source provenance pill (how trustworthy the source's attribution is):
  // grey "?" = LLM-only (may be hallucinated), yellow "~" = the LLM had the source
  // document, green "✓" = quote-checked + agreed by a second LLM. The colour is a
  // `.src-prov-<level>` CSS class. A falsy / unknown level is the "no source yet"
  // case and renders the orange NOSOURCE pill (`.src-todo`) instead. The pill is a
  // <button> so a tap pins its explanatory tooltip on touch (via withTip). Each
  // pill's tooltip explains its own grade, and the About panel ("Sources &
  // provenance") carries the full grade key, so there is no separate blanket "?"
  // caveat. The grade itself comes from the data (generate_data.py
  // PROVENANCE_LEVELS); only the glyph + tooltip live here.
  const PROVENANCE_PILLS = {
    llm: { glyph: "?", tip: "info.provLlm" },
    sourced: { glyph: "~", tip: "info.provSourced" },
    verified: { glyph: "✓", tip: "info.provVerified" },
  };
  // `extra` (optional) is the concrete source shown *first* in the tooltip (the
  // per-claim drug pill's verbatim quote + page ref, or a bibliographic citation),
  // followed after a blank line by the grade explainer (`base`): the actual source
  // is what the reader wants up top, the tier explanation is the footnote under it
  // (.help-tip is white-space:pre-line so the newlines show).
  const makeProvenancePill = (level, extra) => {
    const spec = PROVENANCE_PILLS[level];
    const base = spec ? t(spec.tip) : t("info.provNone");
    const tip = extra ? `${extra}\n\n${base}` : base;
    const cls = spec ? `src-pill src-prov-${level}` : "src-pill src-todo";
    const pill = el("button", cls, spec ? spec.glyph : t("info.noSource"));
    pill.type = "button";
    pill.setAttribute("aria-label", base);
    return withTip(pill, tip);
  };

  // Build the tooltip tail (each source's verbatim quote + its corpus/page ref)
  // shown under a per-claim provenance pill. Shared by the binding rows and the
  // NbN row (both carry quote-level `sources` of the same shape).
  const sourcesTip = (sources) => {
    const corpora = (data.meta && data.meta.sourceCorpora) || {};
    return (sources || [])
      .map((s) => {
        const c = corpora[s.corpus] || {};
        const label = c.ref || c.short || s.corpus;
        const ref = s.page != null
          ? t("info.sourceRef", { corpus: label, page: s.page })
          : label;
        return s.quote ? `“${s.quote}”\n— ${ref}` : `— ${ref}`;
      })
      .join("\n\n");
  };

  // Tooltip for a projection's summary source pill: its bibliographic citations
  // (projection sources are {citation, url, provenance}, no quotes, unlike the
  // drug bindings' quote-level sources). Shown on a structure panel's connection
  // row so the pathway's source is visible from both endpoints, the same role
  // sourcesTip plays for the binding rows.
  const citationsTip = (sources) =>
    (sources || []).map((s) => s.citation).filter(Boolean).join("\n\n");

  // The provenance pill for a drug binding row (shared by the drug panel's "Acts
  // on" list and a target panel's "Interacting drugs" list, the same resolved
  // binding object). A binding with its own quote-level sources shows that grade
  // with the verbatim quote + page in the tooltip; one without falls back to the
  // drug-level Stahl citation at its grade (`llm`: backed by the book at the drug
  // level, just not quote-verified), so every binding carries a grade pill and
  // none ever renders blank. No drug-level "Source(s)" block is shown separately,
  // because the citation now appears here, on the specific binding it backs.
  const bindingProvenancePill = (binding, drug) =>
    binding.sources && binding.sources.length
      ? makeProvenancePill(binding.provenance, sourcesTip(binding.sources))
      : makeProvenancePill(drug.sourceProvenance, citationsTip(drug.sources));

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
    r.appendChild(v);
    facts.appendChild(r);
  };

  // A coloured effect glyph (+ boost / − block / ≈ modulate, in the effect's colour)
  // that replaces the plain colour bar at the head of a drug binding row, so the
  // action's direction reads at a glance. `label` (the localized effect name) is the
  // accessible name; the glyph is otherwise decorative.
  const effectGlyph = (effect, color, label) => {
    const g = el("span", "effect-glyph", EFFECT_GLYPHS[effect] || "·");
    g.style.color = color;
    if (label) g.setAttribute("aria-label", label);
    return g;
  };

  // Shared by the structure / receptor / drug / target views: an external reference
  // link, rendered only for an http(s) url so a stray field can never inject markup.
  // A present link gets its provenance pill (how it was sourced, `provenance` from
  // the data); a missing reference renders the label + the orange TODO pill (the
  // "no source yet" case), so the gap is always visible like a source.
  const appendWiki = (url, provenance) => {
    const ok = typeof url === "string" && /^https?:\/\//i.test(url);
    const wrap = el("div", "info-wiki");
    if (ok) {
      const a = el("a", null, t("info.wikipedia"));
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      wrap.appendChild(a);
      // Name what this pill grades (the link to its left), so it doesn't read as
      // grading the description or the drug. A present link defaults to "sourced"
      // (a real reference), see generate_data.py WIKIPEDIA_DEFAULT_PROVENANCE.
      wrap.appendChild(makeProvenancePill(provenance, t("info.wikiRefGrades")));
    } else {
      wrap.appendChild(el("span", null, t("info.reference")));
      wrap.appendChild(makeProvenancePill(null)); // no reference -> NOSOURCE pill
    }
    body.appendChild(wrap);
    return wrap; // returned so it can anchor a live Wikipedia description below it
  };

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
  // blocked / absent fetch is a no-op, so the panel is unchanged offline. `bakedText`
  // + `bakedSourced` let an already-sourced identical description skip the rewrite.
  const liveWikiDescription = (url, {
    paragraph = null, bakedText = "", bakedSourced = false, anchor = null,
    before = false,
  } = {}) => {
    if (typeof url !== "string" || !/^https?:\/\//i.test(url)) return;
    fetchWikiLead(url, window.__I18N__.lang).then((live) => {
      if (!live || !live.text) return;
      let p = paragraph;
      if (p) {
        if (!p.isConnected) return; // panel re-rendered to something else
        if (live.text === bakedText && bakedSourced) return; // nothing would change
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
      last.appendChild(makeProvenancePill("sourced", t("info.descFromWikipediaLive")));
    });
  };

  // The canonical "intro" block shared by EVERY entity panel (structure / receptor
  // / target / drug): the baked description paragraph (when the datum has one) with
  // its provenance pill, then the Wikipedia reference link + pill *below* the text
  // it backs, then the live-lead refresh. Centralizing it guarantees the same
  // element order and the same sourcing treatment on every panel, instead of each
  // show*() re-composing the two and drifting (which is how the link came to sit
  // above the description on some panels and below it on the drug one). `description`
  // is the baked text (omit for a structure/target, which carry none); a present
  // wiki link with no baked description still gains the live lead *above* it.
  const appendReference = ({
    url, provenance, description = "", descriptionProvenance = "",
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
    const wiki = appendWiki(url, provenance);
    liveWikiDescription(url, paragraph
      ? { paragraph, bakedText: description,
          bakedSourced: descriptionProvenance === "sourced" }
      : { anchor: wiki, before: true });
    return { paragraph, wiki };
  };

  // Shared by the connection + drug views: the source list. Each citation is a
  // link for a verified http(s) url (plain text otherwise) followed by its
  // provenance pill (grey/yellow/green, grading how it was sourced; see
  // makeProvenancePill), so a missing url no longer reads as "TODO" (the pill
  // carries the real status).
  const appendSources = (sources) => {
    if (!sources || !sources.length) return;
    const wrap = el("div", "info-sources");
    const h3 = el(
      "h3", null, sources.length > 1 ? t("info.sources") : t("info.source"));
    wrap.appendChild(h3);
    const ul = el("ul");
    for (const s of sources) {
      const li = el("li");
      if (typeof s.url === "string" && /^https?:\/\//i.test(s.url)) {
        const a = el("a", null, s.citation);
        a.href = s.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        li.appendChild(a);
      } else {
        li.appendChild(document.createTextNode(s.citation));
      }
      li.appendChild(makeProvenancePill(s.provenance));
      ul.appendChild(li);
    }
    wrap.appendChild(ul);
    body.appendChild(wrap);
  };

  // Shared by the receptor + target views: the drugs that act on this target, so
  // you can go from a target to every drug touching it. Grouped by primary drug
  // category (antipsychotic, MAOI, ...) in the meta order, alphabetical within each;
  // every row carries the binding's net-effect swatch (boost / block / modulate) so
  // the kind of interaction is visible, and clicking it opens that drug (focus +
  // panel) via onDrugPick. Omitted entirely when no drug in the dataset acts on it.
  const appendInteractingDrugs = (targetId) => {
    const list = (data.drugsByTarget && data.drugsByTarget.get(targetId)) || [];
    if (!list.length) return;
    const wrap = el("div", "info-bindings info-interactors");
    wrap.appendChild(el(
      "h3", null, `${t("targets.interactingDrugs")} (${list.length})`));

    const cats = data.meta.drugCategoryLabels || {};
    const byCat = new Map();
    for (const item of list) {
      const cat = (item.drug.categories && item.drug.categories[0]) || "other";
      if (!byCat.has(cat)) byCat.set(cat, []);
      byCat.get(cat).push(item);
    }
    // Category order = the meta order first, then any leftover keys (same as the
    // Drugs legend), so the grouping is consistent across the app.
    const order = [...Object.keys(cats),
                   ...[...byCat.keys()].filter((c) => !(c in cats))];
    const done = new Set();
    for (const cat of order) {
      if (done.has(cat) || !byCat.has(cat)) continue;
      done.add(cat);
      const items = byCat.get(cat);
      items.sort((a, b) => a.drug.name.localeCompare(b.drug.name));
      wrap.appendChild(el("h4", "drug-cat", cats[cat] || cat));
      const ul = el("ul");
      for (const { drug, binding } of items) {
        const li = el("li", "clickable");
        if (binding.tentative) li.classList.add("tentative");
        li.appendChild(
          effectGlyph(binding.effect, binding.effectColor, binding.effectLabel));
        const txt = el("div", "bind-text");
        txt.appendChild(el("span", "bind-target", drug.name));
        // A tentative binding gets a "· speculative" tag so the dim+italic row is
        // self-explaining (it rides the dimmed action line, so it reads as muted).
        const parts = [binding.actionLabel, binding.note];
        if (binding.tentative) parts.push(t("drug.speculative"));
        const detail = parts.filter(Boolean).join(" · ");
        if (detail) txt.appendChild(el("span", "bind-action", detail));
        li.appendChild(txt);
        // Source pill, the *same* one shown on the drug panel's "Acts on" row (the
        // same resolved binding + its drug, so the source is shared, not
        // duplicated): a link between drug A and target B carries its provenance on
        // both panels, and falls back to the drug-level Stahl citation when the
        // binding has no quote of its own (see bindingProvenancePill).
        li.appendChild(bindingProvenancePill(binding, drug));
        li.title = `${binding.effectLabel} · ${drug.name}`;
        li.addEventListener("click", () => onDrugPick(drug));
        ul.appendChild(li);
      }
      wrap.appendChild(ul);
    }
    body.appendChild(wrap);
  };

  // One clickable <li> for a pathway that is a member of some grouping (a
  // structure's connections, a circuit's loop, a projection group): a kind swatch,
  // an optional direction glyph, the label text, the pathway's summary source pill,
  // and a click that jumps to the connection via onConnectionPick. Shared so the
  // row markup lives in one place (showStructure rows are relative to the
  // structure; circuit / group rows show the full route).
  const pathwayRow = (proj, glyph, labelText) => {
    const li = el("li");
    li.title = proj.label || "";
    const swatch = el("span", "swatch line");
    swatch.style.background = proj.color || "#fff";
    li.appendChild(swatch);
    if (glyph) li.appendChild(el("span", "conn-dir", glyph));
    li.appendChild(el("span", "conn-label", labelText));
    if (proj.sources && proj.sources.length) {
      li.appendChild(makeProvenancePill(proj.provenance, citationsTip(proj.sources)));
    }
    li.addEventListener("click", () => onConnectionPick(proj));
    return li;
  };

  // A titled "member pathways" list (the circuit + projection-group panels): one
  // pathwayRow per projection, each showing its full from -> to route.
  const appendPathwayList = (titleText, projs) => {
    if (!projs.length) return;
    const wrap = el("div", "info-connections");
    wrap.appendChild(el("h3", null, `${titleText} (${projs.length})`));
    const ul = el("ul");
    for (const proj of projs) {
      const glyph = proj.bidirectional ? "↔" : "→";
      ul.appendChild(pathwayRow(
        proj, null, `${nameOf(proj.from)} ${glyph} ${nameOf(proj.to)}`));
    }
    wrap.appendChild(ul);
    body.appendChild(wrap);
  };

  return {
    show(proj) {
      body.innerHTML = "";
      body.appendChild(el("h2", "info-title", proj.label || t("info.connection")));

      // Route line: from -> to (or <-> for a bidirectional/commissural link).
      body.appendChild(el(
        "div", "info-route",
        `${nameOf(proj.from)} ${proj.bidirectional ? "↔" : "→"} ${nameOf(proj.to)}`,
      ));

      // Kind swatch + kind/transmitter text.
      const meta = el("div", "info-meta");
      const swatch = el("span", "swatch line");
      swatch.style.background = proj.color || "#fff";
      meta.appendChild(swatch);
      // Localized functional kind (falls back to the raw key) + transmitter.
      const kindLabel = (data.meta.kindLabels && data.meta.kindLabels[proj.kind])
        || proj.kind;
      meta.appendChild(el(
        "span", null,
        [kindLabel, proj.neurotransmitter].filter(Boolean).join(" · "),
      ));
      body.appendChild(meta);

      if (proj.description) body.appendChild(el("p", "info-desc", proj.description));

      appendSources(proj.sources);
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
      body.appendChild(el(
        "div", "info-group",
        data.meta.groupLabels[structure.group] || structure.group,
      ));

      // Wikipedia illustration (the lead rotating-brain GIF, else an SVG diagram or
      // an infobox image; resolved by tools/fetch_structure_images.py). These can be
      // multi-MB, so rather than vendor them the viewer HOT-LINKS the Wikimedia url
      // at runtime (CSP img-src allows upload.wikimedia.org), like the live
      // descriptions. A spinner shows while it loads; the whole figure is removed if
      // the load fails (offline / blocked / moved), so a failure degrades to no
      // image. Unlike the drug molecule line-art these are colour, so NOT inverted.
      if (structure.structureImage) {
        const fig = el("figure", "structure-image loading");
        fig.appendChild(el("div", "img-spinner"));
        const img = document.createElement("img");
        img.alt = t("structure.imageAlt", { name: structure.name });
        img.loading = "lazy";
        img.decoding = "async";
        img.addEventListener("load", () => fig.classList.remove("loading"));
        img.addEventListener("error", () => fig.remove());
        img.src = structure.structureImage;
        fig.appendChild(img);
        body.appendChild(fig);
      }

      // External reference (Wikipedia) + its live lead summary, via the shared
      // appendReference (structures carry no baked description, so the live lead,
      // when it arrives, appears above the link).
      appendReference({
        url: structure.wikipedia, provenance: structure.wikipedia_provenance,
      });

      // Source grade backing this region's anatomy (existence / group / position),
      // so even a structure shows a graded source, not "no source". Added before the
      // no-connections early return so it shows for an unconnected region too.
      if (structure.classification_provenance) {
        const facts = el("div", "info-facts");
        addFactRow(facts, t("info.source"), "", null,
          { pill: makeProvenancePill(structure.classification_provenance) });
        body.appendChild(facts);
      }

      // Pathways with this structure at either end, in the data's order.
      const conns = data.projections.filter(
        (p) => p.from === structure.id || p.to === structure.id);
      if (conns.length === 0) {
        body.appendChild(el("p", "info-desc", t("info.noConnections")));
        return;
      }

      const wrap = el("div", "info-connections");
      wrap.appendChild(el(
        "h3", null, `${t("info.connections")} (${conns.length})`));
      const ul = el("ul");
      for (const proj of conns) {
        // Direction relative to *this* structure: → it projects out, ← it
        // receives, ↔ reciprocal/commissural. The row markup (swatch, label,
        // summary source pill, click) is the shared pathwayRow; only the
        // structure-relative glyph + other-endpoint label are computed here.
        const outgoing = proj.from === structure.id;
        const otherId = outgoing ? proj.to : proj.from;
        const glyph = proj.bidirectional ? "↔" : outgoing ? "→" : "←";
        ul.appendChild(pathwayRow(proj, glyph, nameOf(otherId)));
      }
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

      appendReference({
        url: receptor.wikipedia, provenance: receptor.wikipedia_provenance,
        description: receptor.description,
      });

      // Classification facts as label / value rows; the "effect" value carries the
      // sign swatch so the colour matches the dots + legend row.
      const facts = el("div", "info-facts");
      addFactRow(facts, t("receptor.neurotransmitter"), receptor.neurotransmitter);
      addFactRow(facts, t("receptor.type"), receptor.classLabel);
      addFactRow(facts, t("receptor.effect"), receptor.signLabel, receptor.signColor);
      addFactRow(facts, t("receptor.synaptic"), receptor.synapticLabel);
      // Source grade backing the classification facts above (so "why is it
      // excitatory" carries a provenance pill like every other datum). The grade is
      // data (classification_provenance); the read-more Wikipedia link is separate.
      addFactRow(facts, t("info.source"), "", null,
        { pill: makeProvenancePill(receptor.classification_provenance) });
      body.appendChild(facts);

      // Where it is expressed.
      const where = el("div", "info-locations");
      where.appendChild(el("h3", null, t("receptor.foundIn")));
      if (receptor.ubiquitous) {
        where.appendChild(el("p", "info-desc", t("receptor.ubiquitous")));
      } else if (receptor.locationNames.length === 0) {
        where.appendChild(el("p", "info-desc", t("receptor.noRole")));
      } else {
        where.appendChild(locationList(receptor.locationNames, receptor.locations));
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
      appendReference({
        url: target.wikipedia, provenance: target.wikipediaProvenance,
      });

      const facts = el("div", "info-facts");
      addFactRow(facts, t("receptor.type"), target.typeLabel, target.swatchColor);
      addFactRow(facts, t("receptor.system"), target.systemLabel);
      // Source grade backing the type / system / region claims above (so the panel
      // never shows "no source": even an llm grade is a graded source).
      if (target.classificationProvenance) {
        addFactRow(facts, t("info.source"), "", null,
          { pill: makeProvenancePill(target.classificationProvenance) });
      }
      if (facts.childElementCount) body.appendChild(facts);

      // Where it sits (same "Found in" list as a receptor; empty -> no footprint).
      const where = el("div", "info-locations");
      where.appendChild(el("h3", null, t("receptor.foundIn")));
      if (!target.locationNames.length) {
        where.appendChild(el("p", "info-desc", t("receptor.noRole")));
      } else {
        where.appendChild(locationList(target.locationNames, target.locationBases));
      }
      body.appendChild(where);

      // Drugs that act on this target, grouped by category.
      appendInteractingDrugs(target.id);
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

      // Vendored molecular-structure SVG (from Wikipedia, see tools/fetch_molecules.py).
      // It is black/grey line art on transparent; the .mol-structure CSS inverts it
      // to read as light strokes on the dark panel. Absent when no SVG was fetched.
      if (drug.structureImage) {
        const fig = el("figure", "mol-structure");
        const img = document.createElement("img");
        img.src = drug.structureImage;
        img.alt = t("drug.structureAlt", { name: drug.name });
        img.decoding = "async";
        fig.appendChild(img);
        body.appendChild(fig);
      }

      // Description (the drug's Wikipedia lead, baked + live-refreshed) then the
      // Wikipedia link below it, via the shared appendReference. A "sourced"
      // description is the WP lead (CC BY-SA); an "llm" one a mechanism synthesis.
      const { wiki } = appendReference({
        url: drug.wikipedia, provenance: drug.wikipedia_provenance,
        description: drug.description,
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
        const addLookup = (labelKey, href, titleKey) => {
          wiki.appendChild(el("span", "ref-sep", "·"));
          const a = el("a", null, t(labelKey));
          a.href = href;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.title = t(titleKey);
          wiki.appendChild(a);
        };
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
      addFactRow(facts, t("drug.class"), null, null, {
        links: drug.categoryLabels.map((label) => ({
          text: label,
          query: `class:"${label}"`,
        })),
      });
      if (drug.nbn) {
        // The NbN line is quote-sourced from Stahl; show its provenance pill
        // (with the verbatim quote in the tooltip) beside the clickable value.
        const nbnPill = drug.nbnSources && drug.nbnSources.length
          ? makeProvenancePill(drug.nbnProvenance, sourcesTip(drug.nbnSources))
          : null;
        addFactRow(facts, t("drug.nomenclature"), null, null, {
          links: [{ text: drug.nbn, query: `nbn:"${drug.nbn}"` }],
          pill: nbnPill,
        });
      }
      if (facts.childElementCount) body.appendChild(facts);

      // What it binds: one row per target, coloured by the action's net effect.
      const acts = el("div", "info-bindings");
      acts.appendChild(el("h3", null, t("drug.actsOn")));
      if (!drug.bindings.length) {
        acts.appendChild(el("p", "info-desc", t("drug.noTargets")));
      } else {
        const ul = el("ul");
        for (const b of drug.bindings) {
          const li = el("li");
          if (b.tentative) li.classList.add("tentative");
          li.appendChild(effectGlyph(b.effect, b.effectColor, b.effectLabel));
          // Target name (bold) over the action line, stacked so a long target
          // name (e.g. "Serotonin transporter (SERT)") wraps cleanly inside the
          // narrow panel instead of pushing the action off the edge.
          const txt = el("div", "bind-text");
          txt.appendChild(el("span", "bind-target", b.targetName));
          // A tentative binding gets a "· speculative" tag so the dim+italic row is
          // self-explaining (it rides the dimmed action line, so it reads as muted).
          const parts = [b.actionLabel, b.note];
          if (b.tentative) parts.push(t("drug.speculative"));
          const detail = parts.filter(Boolean).join(" · ");
          if (detail) txt.appendChild(el("span", "bind-action", detail));
          li.appendChild(txt);
          // Source pill: this binding's own quote-level source when it has one,
          // else the drug-level Stahl citation (grade llm). Always shown, so the
          // grade is never blank (see bindingProvenancePill).
          li.appendChild(bindingProvenancePill(b, drug));
          li.title = `${b.effectLabel} · ${b.targetName}`;
          // If this binding's target is browsable on its own (in the merged
          // "Receptors & targets" list and focusable), make the row jump to it.
          const tgt = targetById.get(b.target);
          if (tgt && tgt.focusable) {
            li.classList.add("clickable");
            li.addEventListener("click", () => onTargetPick(tgt));
          }
          ul.appendChild(li);
        }
        acts.appendChild(ul);
      }
      body.appendChild(acts);
      // No standalone drug-level "Source(s)" block: the Stahl citation that backs
      // the drug is shown per-binding (each binding's pill above), so a source
      // always refers to a specific datum rather than "the whole drug".
    },

    /**
     * Populate the panel for a *circuit* (clicking a Circuits legend row / search):
     * its name, a sourced description, the structures it loops through (deduped to
     * bases, each clickable to jump to that region) and its member pathways (the
     * projections with both endpoints in the loop, derived not stored), then its
     * sources. Mirrors the structure panel's shape; the member-pathway + region
     * rows reuse the shared pathwayRow / locationList so nothing is duplicated.
     */
    showCircuit(circuit) {
      body.innerHTML = "";
      body.appendChild(el("h2", "info-title", circuit.name));
      body.appendChild(el("div", "info-group", t("circuit.heading")));
      if (circuit.description) {
        body.appendChild(el("p", "info-desc", circuit.description));
      }

      // Structures in the loop, deduped to bases (so the two hemispheres collapse
      // to one row), each clickable to jump to the region via onStructurePick.
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
        const where = el("div", "info-where");
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

      appendSources(circuit.sources);
    },

    /**
     * Populate the panel for a *projection group* (clicking a Projections legend
     * row, in either colour mode): its name, a heading saying whether it groups by
     * transmitter or by sign, a sourced description (baked + live-refreshed from
     * Wikipedia) with the reference link, then its member pathways (the projections
     * whose kind / sign matches the group, derived not stored) and its sources.
     */
    showProjectionGroup(group) {
      body.innerHTML = "";
      body.appendChild(el("h2", "info-title", group.name));
      body.appendChild(el(
        "div", "info-group",
        group.mode === "sign" ? t("group.signHeading") : t("group.kindHeading")));

      // Description (LLM-authored) + the Wikipedia reference below it, then the live
      // lead refresh (upgrades the paragraph to the current WP lead when reachable),
      // via the same shared appendReference every panel uses.
      appendReference({
        url: group.wikipedia, provenance: group.wikipedia_provenance,
        description: group.description,
        descriptionProvenance: group.classification_provenance,
      });

      // Member pathways: the projections this group stands for. In "kind" mode that
      // is every projection of the kind; in "sign" mode every projection folding to
      // the sign. Same derivation the legend uses to colour the arrows, so the panel
      // list always matches what is lit on screen.
      const members = data.projections.filter((p) =>
        group.mode === "sign" ? p.sign === group.key : p.kind === group.key);
      appendPathwayList(t("group.pathways"), members);

      appendSources(group.sources);
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
     * Register the handler run when a clickable Class / Nomenclature value in a drug
     * panel is clicked. Called with a `field:"value"` search query string; the caller
     * opens the search box pre-filled with it.
     */
    onSearch(fn) {
      onSearchPick = fn;
    },
  };
}

/**
 * Build the merged "Receptors & targets" legend section from the live dataset
 * (#receptors-body): the unified `data.targets` list (every modeled receptor plus
 * every non-receptor drug target: transporters, enzymes, channels, receptor
 * groups), grouped by neurotransmitter `system` (in the meta family-label order,
 * then any leftover systems, then an "Other" heading for the system-less ones), so
 * a transporter like SERT sits under "Serotonergic" beside the 5-HT receptors.
 * Each row is coloured by its swatch (a receptor's sign colour, a target's type
 * colour) and, for a non-receptor target, tagged with its type ("transporter",
 * ...). A focusable row is clickable (dim the brain to the regions it sits in +
 * scatter glowing dots, handled by the caller's `onPick`); a footprint-less one
 * (a receptor stub, an unlocated enzyme) renders muted + inert. Returns a
 * `reflect(activeId)` callback that lights the active row and greys the rest.
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
  // Group by system; a null system goes under the "_other" bucket. Receptors come
  // before non-receptor targets within a system because data.targets lists every
  // receptor first (so the array order already gives "5-HT receptors, then SERT").
  const bySystem = new Map();
  for (const tgt of data.targets || []) {
    const key = tgt.system || "_other";
    if (!bySystem.has(key)) bySystem.set(key, []);
    bySystem.get(key).push(tgt);
  }
  // Heading order: the meta family order first, then any leftover real systems,
  // then the "Other" bucket last.
  const order = [
    ...Object.keys(families),
    ...[...bySystem.keys()].filter((k) => k !== "_other" && !(k in families)),
    ...(bySystem.has("_other") ? ["_other"] : []),
  ];
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
function frameVisible({ camera, controls, meshes }, viewName) {
  const box = new THREE.Box3();
  let any = false;
  for (const mesh of meshes) {
    if (mesh.visible) {
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
function createCameraFocus({ camera, controls, meshes }) {
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
     * Re-aim the camera at the currently focused structure after it has moved
     * (the explode slider pushes each region radially outward). Only the orbit
     * pivot (controls.target) is moved onto the structure's new center, so the
     * camera rotates in place to keep tracking it: a reorientation, not a
     * translation, which preserves the distance + angle the user last set. A
     * running framing tween has its destination updated too so the two don't
     * fight over the pivot. No-op when nothing is focused.
     */
    reaimFocused() {
      if (!focused || !focused.visible) return;
      // The mesh's local origin is the structure's center (geometry is built
      // around it), so its world position is where the camera should look.
      focused.getWorldPosition(tmpVec);
      controls.target.copy(tmpVec);
      if (anim) anim.toTarget.copy(tmpVec);
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

  // Frame whenever a view angle is requested, or a subset is isolated.
  if (q.has("view") || q.has("only")) {
    frameVisible(bundle, q.get("view") || "iso");
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
  const stats = meta.provenanceStats;
  if (!stats) return; // dataset predates the tally: leave the block empty

  const h = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  };

  host.appendChild(h("h3", null, t("about.sourcingTitle")));
  host.appendChild(h("p", "about-text", t("about.sourcingIntro")));

  // Grade key: a pill swatch + its meaning, in strongest-to-weakest order, then
  // the NOSOURCE case. The pills reuse the info-panel CSS classes so the legend
  // matches the pills shown next to each source.
  const key = h("ul", "src-key");
  const keyRows = [
    ["src-prov-verified", "✓", "about.gradeVerified"],
    ["src-prov-sourced", "~", "about.gradeSourced"],
    ["src-prov-llm", "?", "about.gradeLlm"],
    ["src-todo", t("info.noSource"), "about.gradeNone"],
  ];
  for (const [cls, glyph, tip] of keyRows) {
    const li = document.createElement("li");
    li.appendChild(h("span", `src-pill ${cls}`, glyph));
    li.appendChild(h("span", null, t(tip)));
    key.appendChild(li);
  }
  host.appendChild(key);

  // Coverage tally: a headline over the factual claims, then a per-kind bar.
  const a = stats.assertions || {};
  const wrap = h("div", "src-stats");
  wrap.appendChild(h("p", "src-stat-headline",
    t("about.sourcingHeadline", { pct: a.pct_backed, total: a.total })));
  const KIND_LABELS = {
    drug_bindings: "about.kindBindings",
    drug_nbn: "about.kindNbn",
    drug_descriptions: "about.kindDescriptions",
    projections: "about.kindProjections",
    receptors: "about.kindReceptors",
    targets: "about.kindTargets",
    structures: "about.kindStructures",
    references: "about.kindReferences",
  };
  for (const [kind, labelKey] of Object.entries(KIND_LABELS)) {
    const c = (stats.by_kind || {})[kind];
    if (!c || !c.total) continue;
    const backed = (c.verified || 0) + (c.sourced || 0);
    const pct = Math.round((100 * backed) / c.total);
    const row = h("div", "src-stat-row");
    row.appendChild(h("span", "src-stat-label", t(labelKey)));
    row.appendChild(h("span", "src-stat-count", `${backed} / ${c.total} (${pct}%)`));
    const bar = h("div", "src-stat-bar");
    const fill = h("span");
    fill.style.width = `${pct}%`;
    bar.appendChild(fill);
    row.appendChild(bar);
    wrap.appendChild(row);
  }
  wrap.appendChild(h("p", "about-text", t("about.coverageNote")));
  host.appendChild(wrap);
}

/** Wire the DOM controls to the scene behaviors. */
function wireControls({ controls, meshes, arrows, labels, focus, selection, projVis, cull }) {
  const autorotate = document.getElementById("autorotate");
  const seeInside = document.getElementById("see-inside");
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
  const legendToggle = document.getElementById("legend-toggle");
  const legendBody = document.getElementById("legend-body");
  const receptorsToggle = document.getElementById("receptors-toggle");
  const receptorsBody = document.getElementById("receptors-body");
  const drugsToggle = document.getElementById("drugs-toggle");
  const drugsBody = document.getElementById("drugs-body");
  const aboutToggle = document.getElementById("about-toggle");
  const aboutBody = document.getElementById("about-body");

  // One collapse-header behaviour shared by the panel, the legend and the about
  // section: toggle aria-expanded + the body's hidden flag. The panel ships
  // expanded; the legend + about ship collapsed (their markup sets the initial
  // aria-expanded / hidden). `onToggle(open)` runs after a click so callers can
  // react (accordion below).
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

  // Structures, Projections, Receptors, Drugs, Legend and About behave as an
  // accordion among themselves: only one open at a time (Controls, above, is
  // exempt). The panel top (language switch + reset/search row) stays visible
  // throughout; the open section grows to fill the tall sidebar via the
  // :has(...) CSS in index.html, so no JS layout class is needed here anymore.
  const sections = [
    { toggle: structuresToggle, body: structuresBody },
    { toggle: projectionsToggle, body: projectionsBody },
    { toggle: receptorsToggle, body: receptorsBody },
    { toggle: drugsToggle, body: drugsBody },
    { toggle: legendToggle, body: legendBody },
    { toggle: aboutToggle, body: aboutBody },
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

  const onExplode = () => {
    const amount = parseFloat(explode.value);
    applyExplode(meshes, amount, arrows);
    // Keep a double-clicked / searched structure centered as it blows outward,
    // by re-aiming (rotating) the camera rather than translating it.
    focus.reaimFocused();
    // Pull the camera back as the regions spread (and zoom back in as they
    // reassemble) so the exploded layout stays framed.
    focus.zoomForExplode(amount);
  };
  explode.addEventListener("input", onExplode);

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
function wireToolbar({ focus, meshes, arrows, data, selection, tabs, selectStructure, selectConnection, selectTarget, selectDrug }) {
  const resetBtn = document.getElementById("reset-view");
  const searchToggle = document.getElementById("search-toggle");
  const searchBox = document.getElementById("search");
  const searchInput = document.getElementById("search-input");
  const searchResults = document.getElementById("search-results");
  // The normal controls; the search box shows in their place (not as a popup),
  // while the reset/search buttons above stay put so the magnifier can toggle
  // back.
  const controlsMain = document.getElementById("controls-main");

  resetBtn.addEventListener("click", () => {
    focus.recenter();
    // Full reset: drop the halo *and* the isolate set, restoring default opacity.
    selection.clear();
  });

  // One searchable index over structures + connections + receptors, each carrying
  // the action to run when it is picked. Built once; structures keep their full
  // name, connections get a hemisphere tag appended so mirrored twins stay
  // distinct, and receptors show their neurotransmitter as a tag (and carry extra
  // `keywords` so the system / mechanism also match, without cluttering the row).
  // The match runs over `label` + `keywords`; only `label` is shown.
  const items = [
    ...meshes.map((mesh) => ({
      label: mesh.userData.structure.name,
      select: () => selectStructure(mesh, { frame: true }),
    })),
    ...arrows.map((arrow) => {
      const tag = connectionSideTag(arrow.projection);
      return {
        label: arrow.projection.label + (tag ? ` · ${tag}` : ""),
        select: () => selectConnection(arrow, { frame: true }),
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
        label: tgt.name + (tag ? ` · ${tag}` : ""),
        keywords: tgt.keywords || "",
        select: () => selectTarget(tgt),
      };
    }),
    // Focusable drugs (those with a binding profile). The row shows the primary
    // class as a tag; keywords carry the full class list + nomenclature + targets.
    // `fields` feeds the structured `class:"..."` / `nbn:"..."` filters (the panel's
    // clickable Class / Nomenclature values), pre-folded for matching.
    ...(data.drugs || []).filter((d) => d.focusable).map((drug) => ({
      label: drug.name + (drug.category ? ` · ${drug.category}` : ""),
      keywords: drug.keywords || "",
      fields: {
        class: foldText(drug.categoryLabels.join(" ")),
        nbn: foldText(drug.nbn || ""),
      },
      select: () => selectDrug(drug),
    })),
  ];

  // Index (among the non-empty rows) of the keyboard-highlighted result, or -1
  // when there is none. Arrow keys move it; Enter activates it (the first by
  // default, since renderResults pre-highlights row 0).
  let activeIndex = -1;
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
    searchResults.innerHTML = "";
    // A structured filter (class:"..." / nbn:"...") is a deliberate "list the whole
    // class" query, so show more rows than the compact name-search list (the results
    // box scrolls). Plain name search stays capped short.
    const cap = field ? 40 : 8;
    const matches = items
      .filter((it) => {
        if (field) {
          const fv = it.fields && it.fields[field];
          if (fv === undefined) return false; // only items with this field
          if (value && !fv.includes(value)) return false;
        }
        if (rest && !foldText(`${it.label} ${it.keywords || ""}`).includes(rest)) {
          return false;
        }
        return true;
      })
      .slice(0, cap);
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
        item.select();
        closeSearch();
      });
      // Hovering syncs the highlight, so mouse + keyboard agree on the active row.
      li.addEventListener("mouseenter", () => highlight(i));
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
    searchInput.value = "";
    renderResults();
    searchInput.focus();
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
 * dim) so the brain returns to its plain state, see the Escape case.
 */
function wireShortcuts(help, tabs, selection) {
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
  // clicking the same toggles a user would so the existing wiring runs.
  const collapseOpen = () => {
    const search = document.getElementById("search");
    if (search && !search.hidden) click("search-toggle");
    for (const id of ["structures-toggle", "projections-toggle", "receptors-toggle",
                      "drugs-toggle", "legend-toggle", "about-toggle"]) {
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
      ["legend-toggle", "legend-body"],
      ["about-toggle", "about-body"],
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
    // With the shortcuts popup open, Esc just closes it (and nothing else fires).
    if (help?.isOpen && event.key === "Escape") {
      help.close();
      event.preventDefault();
      return;
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
      case "k": case "K": sectionNav.reset(); click("legend-toggle"); break;
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

  const open = () => { modal.hidden = false; };
  const close = () => { modal.hidden = true; };
  document.getElementById("shortcuts-toggle")?.addEventListener("click", open);
  document.getElementById("shortcuts-close")?.addEventListener("click", close);
  // A click on the dimmed backdrop (outside the dialog box) closes it.
  modal.addEventListener("click", (event) => {
    if (event.target === modal) close();
  });

  return { open, close, get isOpen() { return !modal.hidden; } };
}

async function main() {
  const { scene, camera, renderer, controls } = initThree();

  // Stamp the version into the panel header (single source: window.__APP_VERSION__
  // from version.js). Done before the data load so it shows even if that fails.
  const versionEl = document.getElementById("app-version");
  if (versionEl && window.__APP_VERSION__) {
    versionEl.textContent = `v${window.__APP_VERSION__}`;
  }

  setStatus(t("status.loading"));
  let data;
  try {
    data = await loadBrainData();
  } catch (err) {
    console.error(err);
    setStatus(""); // clear the loading pill; the error shows as a banner
    window.showErrorBanner?.(t("status.loadError", { msg: err.message }));
    return;
  }

  // Build region meshes and index them for the arrows.
  const meshes = [];
  const meshById = new Map();
  for (const structure of data.structures) {
    const mesh = buildStructureMesh(structure);
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
  const openDetailTab = (key, title, reopen) => tabs.openDetail({ key, title, reopen });

  // Selection + isolation controller: glowing halo on the structure picked by
  // click / double-click / search, plus the legend-driven isolate/dim mode. Owns
  // the structure + arrow opacity so it composes with the transparency slider.
  const selection = createSelection({ meshes, arrows });
  // Pin the selected structure's floating name: while a structure is the active
  // single selection its label stays on regardless of hover, and hovering another
  // region adds its label rather than replacing the pinned one. Driven off the
  // selection highlight so every path that selects a structure (3D click, search,
  // a related-structure panel row) behaves identically, and any non-structure
  // focus (arrow / target / drug) or a clear drops the pin automatically.
  selection.onHighlight((mesh) => labels.setPinned(mesh));
  // When the last detail tab is closed, nothing is selected any more: clear the
  // 3D focus (halo / isolate / dim / dots) so the scene matches the empty strip.
  tabs.setOnEmpty(() => selection.clear());

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
  const focusTarget = (tgt, { frame = false } = {}) => {
    const meshSet = targetMeshesOf(tgt);
    selection.setCircuit(meshSet, []);
    receptorMarkers.show(meshSet, tgt.swatchColor);
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
  const focusDrug = (drug, { frame = false } = {}) => {
    const meshSet = drugMeshesOf(drug);
    const flowArrows = flowArrowsOf(drug);
    selection.setCircuit(meshSet, flowArrows);
    drugAnim.show(drug, meshById);
    circuitAnim.play(flowArrows); // no-op for a drug with no mapped pathways
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
  const focus = createCameraFocus({ camera, controls, meshes });
  controls.addEventListener("start", () => focus.cancel());

  // "See inside" mode: hide the near hemisphere so the deep nuclei show through.
  const cull = createNearCull({ meshes, camera, controls });

  // Every way of picking content (click/tap, double-click, search, a
  // structure-panel connection row) funnels through these two helpers, so the
  // "halo it + label/panel it + maybe frame the camera" sequence lives in one
  // place instead of being copy-pasted at each entry point. `frame` moves the
  // camera (search / double-click); a plain click leaves the view where it is.
  const selectStructure = (mesh, { frame = false } = {}) => {
    if (frame) focus.focusStructure(mesh);
    // select() drives selection.onHighlight, which pins this structure's label on
    // (so the name stays put after the pointer leaves, and survives hovering other
    // regions), so no explicit setHovered is needed here.
    selection.select(mesh);
    const structure = mesh.userData.structure;
    info.showStructure(structure);
    openDetailTab(`structure:${structure.id}`, structure.base_name || structure.name,
      () => selectStructure(mesh));
  };
  // A projection has no id field, but a from->to pair is unique per pathway (the
  // hemispheres differ), so it keys the tab. The reopen re-halos the arrow when
  // one was built; a pathway with no drawn arrow just re-renders the panel.
  const connectionKey = (proj) => `connection:${proj.from}->${proj.to}`;
  const selectConnection = (arrow, { frame = false } = {}) => {
    if (frame) focus.focusConnection(arrow);
    selection.selectArrow(arrow);
    const proj = arrow.projection;
    info.show(proj);
    openDetailTab(connectionKey(proj), proj.label || t("info.connection"),
      () => selectConnection(arrow));
  };

  // Clicking a connection row inside a structure panel jumps to that pathway
  // (frames it, halos the arrow, swaps in the connection panel) just like
  // picking the connection in search.
  info.onConnection((proj) => {
    const arrow = arrows.find((a) => a.projection === proj);
    if (arrow) { selectConnection(arrow, { frame: true }); return; }
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
    if (mesh) selectStructure(mesh, { frame: true });
  });

  // Clicking a drug in a receptor / target panel's "Interacting drugs" list focuses
  // that drug (dim + animation + drug panel + tab), exactly like a Drugs legend row
  // / drug search pick, so you can go from a target to every drug acting on it.
  info.onDrug(selectDrug);

  // Both hemispheres (plus midline singletons) sharing a clicked mesh's base, so
  // a double-click isolates the same pair a legend row click does. The id base is
  // the structure id minus its _R/_L hemisphere suffix (midline ids have none).
  const baseOf = (id) => id.replace(/_[LR]$/, "");
  const isolateGroupFor = (mesh) => {
    const base = baseOf(mesh.userData.structure.id);
    return meshes.filter((m) => baseOf(m.userData.structure.id) === base);
  };

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
  const focusCircuit = (circuit, { frame = false } = {}) => {
    const cMeshes = circuitMeshesOf(circuit);
    const cArrows = arrowsAmong(new Set(cMeshes));
    selection.setCircuit(cMeshes, cArrows);
    circuitAnim.play(cArrows);
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
  const focusProjectionGroup = (group, { frame = false } = {}) => {
    const gArrows = groupArrowsOf(group);
    const gMeshes = [...new Set(gArrows.flatMap((a) => [a.fromMesh, a.toMesh]))];
    selection.setCircuit(gMeshes, gArrows); // pin the arrows, no pulse
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
  // segmented control under "Hide projections". Picking an option recolours the
  // arrows and rebuilds the Projections legend rows to match. The switch lives
  // inside #projections-actions, which buildLegend preserves as a node across
  // rebuilds, so these listeners survive a rebuild.
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

  wireControls({ controls, meshes, arrows, labels, focus, selection, projVis, cull });
  const toolbar = wireToolbar({ focus, meshes, arrows, data, selection, tabs, selectStructure, selectConnection, selectTarget, selectDrug });
  // A drug panel's clickable Class / Nomenclature opens search with a structured
  // filter (class:"..." / nbn:"...") so you can pivot to the whole class.
  info.onSearch(toolbar.openSearchWithQuery);
  const shortcutsHelp = wireShortcutsHelp(); // the "?" / keyboard-button popup
  wireShortcuts(shortcutsHelp, tabs, selection); // single-key shortcuts (n/s/l/p/k/c/r/m/f/?/Esc) + Tab cycles detail tabs
  projVis.apply(); // established arrows visible, tentative ones start hidden
  // Honor screenshot/deep-link view params (?only=, ?view=, ?explode=, ...).
  applyViewParams({ scene, camera, controls, meshes, arrows, labels });
  setStatus("");
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
    // When the dev / WIP banner is up (DEV=1 container; same flag dev-banner.js
    // reads), present the brain a little lower + further back so it sits clear
    // below the banner. Done before intro.start() so the captured resting pose
    // (what the intro settles on) already includes it.
    if ((window.__APP_CONFIG__ || {}).dev === "1") {
      camera.position.multiplyScalar(DEV_BANNER_UNZOOM);
      controls.target.y += DEV_BANNER_DROP;
      controls.update();
    }
    intro.start();
  }

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
    if (focus.tick()) active = true;
    if (circuitAnim.tick()) active = true;
    if (receptorMarkers.tick()) active = true;
    if (drugAnim.tick()) active = true;
    if (controls.update()) active = true;
    if (active) needsRender = true;
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
