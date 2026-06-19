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
import { buildArrows, PROJECTION_COLORS } from "./arrows.js";
import { createLabels } from "./labels.js";

// Explode slider is 0..1; this is how much extra radial distance the most
// outward regions travel at slider = 1 (as a multiple of their base distance
// from the brain center). Large enough that full separation spreads the regions
// well apart (the deep nuclei get plenty of room to be inspected); the camera
// maxDistance (see initThree) is comfortably beyond the farthest region so the
// user can zoom out to see the whole spread.
const EXPLODE_STRENGTH = 2.5;

// Intro animation: on a plain page load the brain starts fully blown out and
// settles together into the assembled whole over this many milliseconds. Tuned
// to feel swift but legible; eased so it departs and arrives smoothly.
const INTRO_DURATION_MS = 1700;

/** Update a small status line (also visible as a fallback if eruda is closed). */
function setStatus(message, isError = false) {
  const el = document.getElementById("status");
  if (!el) return;
  el.textContent = message;
  el.classList.toggle("error", isError);
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
  camera.position.set(9, 4.5, 13);

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
  controls.maxDistance = 60;
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

/**
 * Auto-play intro: start the regions fully blown out and let them glide back
 * together into the assembled brain. Drives the explode amount (and the slider,
 * so the UI stays in sync) each frame; advanced once per frame by `tick()` from
 * the render loop. `cancel()` stops it so a manual grab of the explode slider
 * always wins. Uses easeInOutCubic for a smooth departure + gentle settle.
 * @param {{meshes:THREE.Mesh[], arrows:object[], slider:HTMLInputElement}} deps
 */
function createIntroAnimation({ meshes, arrows, slider }) {
  const FROM = 1; // fully blown out (slider max)
  const TO = 0; // assembled whole
  let startTime = null; // set on the first tick so load jank isn't counted
  let running = false;

  // easeInOutCubic: starts and ends at rest, fastest through the middle.
  const ease = (t) =>
    t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

  const apply = (amount) => {
    // Set the slider directly (no input event) so this doesn't trip the
    // user-input cancel listener wired alongside it.
    slider.value = String(amount);
    applyExplode(meshes, amount, arrows);
  };

  return {
    start() {
      running = true;
      startTime = null;
      apply(FROM);
    },
    cancel() {
      running = false;
    },
    tick() {
      if (!running) return;
      if (startTime === null) startTime = performance.now();
      const t = Math.min(1, (performance.now() - startTime) / INTRO_DURATION_MS);
      apply(FROM + (TO - FROM) * ease(t));
      if (t >= 1) running = false;
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
  let onIsolateChange = () => {}; // legend-greying hook, set via onIsolate()
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
    onIsolateChange(active ? isolated : null, isolatedArrows);
  }

  return {
    /** Record the transparency slider value (composes with isolate dimming). */
    setBaseOpacity(o) {
      baseOpacity = o;
      apply();
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
     * Register the legend-greying callback, invoked with the live isolate set
     * (or null when nothing is isolated) on every change. Applied once now so
     * the legend reflects the current state immediately.
     */
    onIsolate(fn) {
      onIsolateChange = fn;
      apply();
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

// Human-friendly headings per structure `group` value, in display order. A
// structure whose group is missing here is left out of the legend, so keep this
// in sync with the groups used in generate_data.py.
const GROUP_LABELS = {
  lobe: "Lobes",
  basal_ganglia: "Basal ganglia / deep nuclei",
  diencephalon: "Diencephalon",
  limbic: "Limbic",
  hindbrain: "Hindbrain",
};

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
function buildLegend(data, meshById, arrows, selection) {
  // Populate the collapsible body, not the panel itself, so the always-visible
  // "Legend" toggle header (in index.html) is left untouched. The action buttons
  // ("Show all names" / "Hide projections") live in a #legend-actions container
  // authored in the HTML; keep that exact node (it carries the wireControls click
  // handlers) as the sole survivor and append the generated category rows after
  // it, so the buttons stay first.
  const legend = document.getElementById("legend-body");
  const actions = document.getElementById("legend-actions");
  if (actions) legend.replaceChildren(actions);
  else legend.replaceChildren();

  // Remember each structure row + the meshes it stands for, so the isolate state
  // can grey the ones that aren't selected. Headings are tracked too: clicking a
  // category heading toggles every structure under it at once.
  const structureRows = [];
  const groupHeadings = [];

  for (const [group, heading] of Object.entries(GROUP_LABELS)) {
    const inGroup = data.structures.filter((s) => s.group === group);
    if (inGroup.length === 0) continue;
    const h = document.createElement("h2");
    h.textContent = heading;
    legend.appendChild(h);

    // Collapse left/right twins by cleaned name, but gather *both* hemispheres'
    // meshes under that one row so isolating it toggles the pair together.
    const byLabel = new Map();
    for (const s of inGroup) {
      const pretty = s.name.replace(/^(Left|Right)\s+/i, "");
      const label = pretty.charAt(0).toUpperCase() + pretty.slice(1);
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
      const row = addLegendItem(legend, entry.color, label);
      // Clicking the row toggles its structure(s) in the isolate/focus set.
      row.classList.add("clickable");
      row.addEventListener("click", () => selection.toggleIsolate(entry.meshes));
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
  const ntRows = [];
  let activeNt = null;
  const neurotransmitters = [
    ...new Set(data.projections.map((p) => p.neurotransmitter).filter(Boolean)),
  ];
  if (neurotransmitters.length > 0) {
    const h = document.createElement("h2");
    h.textContent = "Projections";
    legend.appendChild(h);
    for (const nt of neurotransmitters) {
      const ntArrows = arrows.filter((a) => a.projection.neurotransmitter === nt);
      // The kind (hence colour) carrying this transmitter, read off its arrows.
      const kind = ntArrows[0] && ntArrows[0].projection.kind;
      const label = kind ? `${nt} (${kind})` : nt;
      const row = addLegendItem(legend, PROJECTION_COLORS[kind] || "#fff", label, true);
      // Endpoints of those arrows, kept opaque so an isolated transmitter still
      // reads as connecting real regions rather than floating in a dimmed brain.
      const ntMeshes = [...new Set(ntArrows.flatMap((a) => [a.fromMesh, a.toMesh]))];
      row.classList.add("clickable");
      row.addEventListener("click", () => {
        if (activeNt === nt) selection.clear();
        else selection.setCircuit(ntMeshes, ntArrows);
      });
      ntRows.push({ row, nt, arrowSet: new Set(ntArrows) });
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
    h.textContent = "Circuits";
    legend.appendChild(h);
    for (const circuit of data.circuits) {
      const meshes = circuit.structures.map((id) => meshById.get(id)).filter(Boolean);
      const meshSet = new Set(meshes);
      const circuitArrows = arrows.filter(
        (a) => meshSet.has(a.fromMesh) && meshSet.has(a.toMesh));
      // Neutral swatch (a circuit has no single colour) drawn as a thin bar.
      const row = addLegendItem(legend, "#b0b0b0", circuit.name, true);
      row.classList.add("clickable");
      const entry = { row, id: circuit.id, meshes, meshSet, arrows: circuitArrows };
      row.addEventListener("click", () => {
        if (activeCircuitId === circuit.id) selection.clear();
        else selection.setCircuit(meshes, circuitArrows);
      });
      circuitRows.push(entry);
    }
  }

  // Reflect the isolate set onto the legend: the isolated rows stay lit, the
  // rest grey out. `null` (nothing isolated) clears both states. A heading lights
  // only when its whole group is isolated; a circuit row lights only when the
  // isolate set is *exactly* that circuit (so toggling a structure unlights it);
  // a neurotransmitter row lights only when the pinned-arrow set is exactly that
  // transmitter's arrows. `focusedArrows` is the pinned-arrow set (empty unless a
  // circuit/neurotransmitter is focused).
  selection.onIsolate((isolated, focusedArrows) => {
    // Detect a neurotransmitter focus first: the pinned-arrow set is exactly one
    // transmitter's arrows. Such a focus dims every structure (only that
    // transmitter's arrows + endpoints stay opaque in the scene), so its
    // structure/heading rows grey out rather than lighting up; that lit-row noise
    // only makes sense for a circuit.
    const matchesNt = (arrowSet) => arrowSet.size > 0 && focusedArrows
      && focusedArrows.size === arrowSet.size
      && [...arrowSet].every((a) => focusedArrows.has(a));
    activeNt = null;
    for (const { nt, arrowSet } of ntRows) if (matchesNt(arrowSet)) activeNt = nt;
    const projFocus = activeNt !== null;

    for (const { row, meshes } of structureRows) {
      const selected = Boolean(isolated) && !projFocus && meshes.some((m) => isolated.has(m));
      row.classList.toggle("selected", selected);
      row.classList.toggle("dimmed", Boolean(isolated) && !selected);
    }
    for (const { row, arrowSet } of ntRows) {
      const selected = matchesNt(arrowSet);
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
  });
}

/**
 * Build the connection info panel controller. The panel is populated from a
 * projection record on demand (clicking an arrow, or picking a connection in the
 * search), showing the pathway name, its route, kind + neurotransmitter, a one-
 * line description, and its sources (a real http(s) url renders as a link, the
 * placeholder "TODO" url as plain text). DOM is built fresh on each show so the
 * panel never leaks a previous connection's fields.
 * @param {import("./data.js").BrainData} data  Used to resolve endpoint ids to names.
 * @returns {{show: (proj: object) => void, hide: () => void}}
 */
function createInfoPanel(data) {
  const panel = document.getElementById("info-panel");
  const body = document.getElementById("info-body");
  const closeBtn = document.getElementById("info-close");
  const nameOf = (id) => data.byId.get(id)?.name || id;
  closeBtn.addEventListener("click", () => { panel.hidden = true; });

  // Set by the caller (onConnection): what to do when a connection row in a
  // structure panel is clicked. The panel only knows projections, so the caller
  // maps the projection to its arrow and does the framing/halo/connection-panel.
  let onConnectionPick = () => {};

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  return {
    show(proj) {
      body.innerHTML = "";
      body.appendChild(el("h2", "info-title", proj.label || "Connection"));

      // Route line: from -> to (or <-> for a bidirectional/commissural link).
      body.appendChild(el(
        "div", "info-route",
        `${nameOf(proj.from)} ${proj.bidirectional ? "↔" : "→"} ${nameOf(proj.to)}`,
      ));

      // Kind swatch + kind/transmitter text.
      const meta = el("div", "info-meta");
      const swatch = el("span", "swatch line");
      swatch.style.background = PROJECTION_COLORS[proj.kind] || "#fff";
      meta.appendChild(swatch);
      meta.appendChild(el(
        "span", null,
        [proj.kind, proj.neurotransmitter].filter(Boolean).join(" · "),
      ));
      body.appendChild(meta);

      if (proj.description) body.appendChild(el("p", "info-desc", proj.description));

      if (proj.sources && proj.sources.length) {
        const wrap = el("div", "info-sources");
        wrap.appendChild(el("h3", null, proj.sources.length > 1 ? "Sources" : "Source"));
        const ul = el("ul");
        for (const s of proj.sources) {
          const li = el("li");
          if (typeof s.url === "string" && /^https?:\/\//i.test(s.url)) {
            const a = el("a", null, s.citation);
            a.href = s.url;
            a.target = "_blank";
            a.rel = "noopener noreferrer";
            li.appendChild(a);
          } else {
            // No verified link yet: show the citation plus a muted TODO marker.
            li.appendChild(document.createTextNode(s.citation));
            li.appendChild(el("span", "src-todo", " (link: TODO)"));
          }
          ul.appendChild(li);
        }
        wrap.appendChild(ul);
        body.appendChild(wrap);
      }
      panel.hidden = false;
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
        "div", "info-group", GROUP_LABELS[structure.group] || structure.group,
      ));

      // Pathways with this structure at either end, in the data's order.
      const conns = data.projections.filter(
        (p) => p.from === structure.id || p.to === structure.id);
      if (conns.length === 0) {
        body.appendChild(el("p", "info-desc", "No mapped connections yet."));
        panel.hidden = false;
        return;
      }

      const wrap = el("div", "info-connections");
      wrap.appendChild(el(
        "h3", null, `Connections (${conns.length})`));
      const ul = el("ul");
      for (const proj of conns) {
        // Direction relative to *this* structure: → it projects out, ← it
        // receives, ↔ reciprocal/commissural.
        const outgoing = proj.from === structure.id;
        const otherId = outgoing ? proj.to : proj.from;
        const glyph = proj.bidirectional ? "↔" : outgoing ? "→" : "←";

        const li = el("li");
        li.title = proj.label || "";
        const swatch = el("span", "swatch line");
        swatch.style.background = PROJECTION_COLORS[proj.kind] || "#fff";
        li.appendChild(swatch);
        li.appendChild(el("span", "conn-dir", glyph));
        li.appendChild(el("span", "conn-label", nameOf(otherId)));
        li.addEventListener("click", () => onConnectionPick(proj));
        ul.appendChild(li);
      }
      wrap.appendChild(ul);
      body.appendChild(wrap);
      panel.hidden = false;
    },

    /** Register the handler run when a structure-panel connection row is clicked. */
    onConnection(fn) {
      onConnectionPick = fn;
    },

    hide() {
      panel.hidden = true;
    },
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
    /** Abort any running tween (used when the user starts interacting). */
    cancel() {
      anim = null;
    },
    /** Advance the active tween; call once per frame before controls.update(). */
    tick() {
      if (!anim) return;
      const t = Math.min(1, (performance.now() - anim.start) / anim.duration);
      const e = t * t * (3 - 2 * t); // smoothstep ease in/out
      controls.target.lerpVectors(anim.fromTarget, anim.toTarget, e);
      camera.position.lerpVectors(anim.fromPos, anim.toPos, e);
      if (t >= 1) anim = null;
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
  // ?ui=0 hides the control panel (which now nests the toolbar + legend) and the
  // info panel for clean, uncluttered shots (e.g. reviewing a single shape).
  if (q.get("ui") === "0") {
    for (const id of ["controls", "info-panel"]) {
      const el = document.getElementById(id);
      if (el) el.style.display = "none";
    }
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

/** Wire the DOM controls to the scene behaviors. */
function wireControls({ controls, meshes, arrows, labels, focus, selection }) {
  const autorotate = document.getElementById("autorotate");
  const explode = document.getElementById("explode");
  const transparency = document.getElementById("transparency");
  const toggleNames = document.getElementById("toggle-names");
  const toggleProjections = document.getElementById("toggle-projections");
  const controlsToggle = document.getElementById("controls-toggle");
  const controlsBody = document.getElementById("controls-body");
  const legendToggle = document.getElementById("legend-toggle");
  const legendBody = document.getElementById("legend-body");
  const aboutToggle = document.getElementById("about-toggle");
  const aboutBody = document.getElementById("about-body");

  // One collapse-header behaviour shared by the panel, the legend and the about
  // section: toggle aria-expanded + the body's hidden flag. The panel ships
  // expanded; the legend + about ship collapsed (their markup sets the initial
  // aria-expanded / hidden).
  const wireCollapse = (toggle, body) => {
    toggle.addEventListener("click", () => {
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!expanded));
      body.hidden = expanded;
    });
  };
  wireCollapse(controlsToggle, controlsBody);
  wireCollapse(legendToggle, legendBody);
  wireCollapse(aboutToggle, aboutBody);

  // About: point the "Source code" link at the configured sourceUrl (from
  // app-config.js, default the public site). Drop the row if it isn't a valid
  // http(s) url, so a broken/empty config never shows a dead link.
  const aboutSource = document.getElementById("about-source");
  const sourceUrl = String((window.__APP_CONFIG__ || {}).sourceUrl || "").trim();
  if (aboutSource) {
    if (/^https?:\/\//i.test(sourceUrl)) aboutSource.href = sourceUrl;
    else document.getElementById("about-source-row")?.remove();
  }

  controls.autoRotate = autorotate.checked;
  controls.autoRotateSpeed = 1.5;
  autorotate.addEventListener("change", () => {
    controls.autoRotate = autorotate.checked;
  });

  const onExplode = () => {
    applyExplode(meshes, parseFloat(explode.value), arrows);
    // Keep a double-clicked / searched structure centered as it blows outward,
    // by re-aiming (rotating) the camera rather than translating it.
    focus.reaimFocused();
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

  // Button that forces every structure label on/off at once (vs. hover, which
  // shows just one). aria-pressed + an .active class reflect the state.
  let allNames = false;
  toggleNames.addEventListener("click", () => {
    allNames = !allNames;
    labels.setShowAll(allNames);
    toggleNames.setAttribute("aria-pressed", String(allNames));
    toggleNames.classList.toggle("active", allNames);
    toggleNames.textContent = allNames ? "Hide all names" : "Show all names";
  });

  // Hide/show every projection arrow at once (off by default: arrows shown).
  // Toggles each arrow group's visibility and refreshes labels so the connection
  // labels (which key off group.visible) follow; hidden arrows also stop being
  // pickable since the pick helpers skip group.visible=false.
  let projectionsHidden = false;
  toggleProjections.addEventListener("click", () => {
    projectionsHidden = !projectionsHidden;
    for (const arrow of arrows) arrow.setVisible(!projectionsHidden);
    labels.refresh();
    toggleProjections.setAttribute("aria-pressed", String(projectionsHidden));
    toggleProjections.classList.toggle("active", projectionsHidden);
    toggleProjections.textContent = projectionsHidden ? "Show projections" : "Hide projections";
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
 * normal controls. Typing filters both structures (by name) and connections (by
 * pathway label); clicking a result (or pressing Enter to take the first one)
 * centers the camera on it. Picking a structure shows its label; picking a
 * connection frames its two endpoints and opens the info panel.
 * @param {{focus:ReturnType<typeof createCameraFocus>, meshes:THREE.Mesh[],
 *   arrows:import("./arrows.js").ProjectionArrow[], labels:object,
 *   info:ReturnType<typeof createInfoPanel>,
 *   selection:ReturnType<typeof createSelection>}} deps
 */
function wireToolbar({ focus, meshes, arrows, labels, info, selection }) {
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

  // One searchable index over structures + connections, each carrying the action
  // to run when it is picked. Built once; structures keep their full name, while
  // connections get a hemisphere tag appended so mirrored twins stay distinct.
  const items = [
    ...meshes.map((mesh) => ({
      label: mesh.userData.structure.name,
      select: () => {
        focus.focusStructure(mesh);
        labels.setHovered(mesh);
        selection.select(mesh);
        info.showStructure(mesh.userData.structure);
      },
    })),
    ...arrows.map((arrow) => {
      const tag = connectionSideTag(arrow.projection);
      return {
        label: arrow.projection.label + (tag ? ` · ${tag}` : ""),
        select: () => {
          focus.focusConnection(arrow);
          info.show(arrow.projection);
          selection.selectArrow(arrow);
        },
      };
    }),
  ];

  // Rebuild the (capped) result list from the current query. An empty query
  // lists everything so the box doubles as a browsable index.
  function renderResults() {
    const q = searchInput.value.trim().toLowerCase();
    searchResults.innerHTML = "";
    const matches = items
      .filter((it) => it.label.toLowerCase().includes(q))
      .slice(0, 8);
    if (matches.length === 0) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = "No match";
      searchResults.appendChild(li);
      return;
    }
    for (const item of matches) {
      const li = document.createElement("li");
      li.textContent = item.label;
      li.addEventListener("click", () => {
        item.select();
        closeSearch();
      });
      searchResults.appendChild(li);
    }
  }

  function openSearch() {
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

  searchToggle.addEventListener("click", () => {
    if (searchBox.hidden) openSearch();
    else closeSearch();
  });
  searchInput.addEventListener("input", renderResults);
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      const first = searchResults.querySelector("li:not(.empty)");
      if (first) first.click();
    } else if (event.key === "Escape") {
      closeSearch();
    }
  });
}

async function main() {
  const { scene, camera, renderer, controls } = initThree();

  // Stamp the version into the panel header (single source: window.__APP_VERSION__
  // from version.js). Done before the data load so it shows even if that fails.
  const versionEl = document.getElementById("app-version");
  if (versionEl && window.__APP_VERSION__) {
    versionEl.textContent = `v${window.__APP_VERSION__}`;
  }

  setStatus("Loading brain data...");
  let data;
  try {
    data = await loadBrainData();
  } catch (err) {
    console.error(err);
    setStatus(""); // clear the "Loading..." pill; the error shows as a banner
    window.showErrorBanner?.(
      `Could not load brain data: ${err.message}. Are you serving over HTTP? (see CLAUDE.md)`,
    );
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
  const info = createInfoPanel(data);

  // Selection + isolation controller: glowing halo on the structure picked by
  // click / double-click / search, plus the legend-driven isolate/dim mode. Owns
  // the structure + arrow opacity so it composes with the transparency slider.
  const selection = createSelection({ meshes, arrows });

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
      info.show(arrow.projection);
      selection.selectArrow(arrow);
      return true;
    }
    const mesh = structHit ? structHit.object : null;
    // A structure opens its own panel (name, group, connections); a true miss on
    // empty space closes the panel.
    if (mesh) info.showStructure(mesh.userData.structure);
    else info.hide();
    selection.select(mesh);
    labels.setHovered(mesh);
    return true;
  };

  // Mouse: hover a region to reveal its name. Mouse-only so that touch-drag
  // rotation doesn't flicker labels (touch uses tap, below).
  canvas.addEventListener("pointermove", (event) => {
    if (event.pointerType !== "mouse") return;
    labels.setHovered(pickAt(event.clientX, event.clientY));
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

  // Double-click to focus: on a structure, center and frame it; on empty space,
  // recenter the whole brain (same as the reset button). The move is a smooth
  // tween advanced in the render loop; grabbing the controls cancels it so a
  // drag always wins.
  const focus = createCameraFocus({ camera, controls, meshes });
  controls.addEventListener("start", () => focus.cancel());

  // Clicking a connection row inside a structure panel jumps to that pathway:
  // frame its endpoints, halo the arrow, and swap in the connection panel (same
  // behaviour as picking the connection in search).
  info.onConnection((proj) => {
    const arrow = arrows.find((a) => a.projection === proj);
    if (!arrow) { info.show(proj); return; }
    focus.focusConnection(arrow);
    info.show(proj);
    selection.selectArrow(arrow);
  });

  canvas.addEventListener("dblclick", (event) => {
    const mesh = pickAt(event.clientX, event.clientY);
    if (mesh) {
      focus.focusStructure(mesh);
      labels.setHovered(mesh);
      selection.select(mesh);
      info.showStructure(mesh.userData.structure);
    } else {
      // Double-click on empty space is a full reset, same as the reset button.
      focus.recenter();
      selection.clear();
    }
  });

  buildLegend(data, meshById, arrows, selection);
  wireControls({ controls, meshes, arrows, labels, focus, selection });
  wireToolbar({ focus, meshes, arrows, labels, info, selection });
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
  const intro = createIntroAnimation({ meshes, arrows, slider: explodeSlider });
  explodeSlider.addEventListener("input", () => intro.cancel());
  if (!new URLSearchParams(window.location.search).has("explode")) {
    intro.start();
  }

  renderer.setAnimationLoop(() => {
    // Advance the intro + any focus/recenter tween before controls.update()
    // reads the target + camera position for this frame.
    intro.tick();
    focus.tick();
    controls.update();
    renderer.render(scene, camera);
    // CSS2D labels render as a separate DOM pass after the WebGL frame.
    labels.render(scene, camera);
  });
}

main();
