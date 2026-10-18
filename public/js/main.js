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
import { geometryFromArrays } from "./sdf.js";
import { loadBakedMeshes } from "./baked-meshes.js";
import { createMeshBudget } from "./sdf-quality.js";
import { createLoadingScreen } from "./loading.js";
import { buildArrows } from "./arrows.js";
import { createLabels } from "./labels.js";
import { createCircuitAnimation } from "./circuit-anim.js";
import { createReceptorMarkers } from "./receptor-markers.js";
import { createDrugAnimation } from "./drug-anim.js";
import { animSettings } from "./anim-settings.js";
import { createChangelog } from "./changelog.js";
import { createNodeBrowser } from "./node-browser.js";
import { KIND_LABELS } from "./kinds.js";
import { createSimulation } from "./simulation.js";
import { createUrlState } from "./url-state.js";
import { foldText } from "./search/query.js";
import { formatHalfLife } from "./panel/format.js";
import { stripSide } from "./util.js";
import { buildEffectLegend, buildEnzymeLegend } from "./legend/browse.js";
import { buildTargetLegend } from "./legend/targets.js";
import { buildDrugLegend } from "./legend/drugs.js";
import { buildLegend, createProjectionVisibility } from "./legend/anatomy.js";
import { buildLegendKey } from "./legend/key.js";
import { createPanelTabs } from "./panel/tabs.js";
import { initThree, setRepaint } from "./scene/setup.js";
import { applyExplode, createArrowWidth } from "./scene/explode.js";
import { createSeeInside, isPickableMesh } from "./scene/see-inside.js";
import { createAdaptiveQuality } from "./scene/quality.js";
import { createIntroAnimation } from "./scene/intro.js";
import { createSelection } from "./scene/selection.js";
import { applyViewParams, createCameraFocus } from "./scene/camera.js";
import {
  wireAboutModal, wireImageLightbox, wireLegendModal, wireModal, wireShortcutsHelp,
  wireSourcingModal,
} from "./about/modals.js";
import { buildAboutSourcing, GRADE_LABELS } from "./about/sourcing.js";
import { createInfoPanel } from "./panel/info.js";
import { wireControls } from "./boot/controls.js";
import { TYPING_SETTLE_MS, wireToolbar } from "./boot/toolbar.js";
import { wireShortcuts } from "./boot/shortcuts.js";
import { createViewerTour } from "./boot/tour-steps.js";
import { wireUrlBindings } from "./boot/url-bindings.js";
import { wireCanvasPicking } from "./boot/picking.js";
import { wireHeaderToggles } from "./boot/header-toggles.js";
import { wireSpeedSlider } from "./boot/speed-slider.js";
import { AUTOMATED_VIEW, HAS_EXPLODE, TOUR_FORCED } from "./boot/query.js";

// UI string lookup (js/i18n.js, a classic script that ran before this module).
// `t(key, vars)` returns the current-language UI string; data strings are
// already resolved to the chosen language by js/data.js.
const { t, ofNoun } = window.__I18N__;

// When the dev / WIP banner is shown (DEV=1 container), the brain is presented a
// touch lower and further back so it sits clear below the banner: the resting
// camera is pulled out by this factor and the look-point lifted by this many
// world units (so the brain renders lower in the frame).
const DEV_BANNER_UNZOOM = 1.15;
const DEV_BANNER_DROP = 1.6;

async function main() {
  const { scene, camera, renderer, controls, baseDpr, theme } = initThree();

  // Stamp the version into every [data-app-version] slot (the panel header and the
  // loading overlay's title; single source: window.__APP_VERSION__ from version.js).
  // Done before the data load so it shows even if that fails; a new display spot is
  // then markup-only, no second lookup here.
  if (window.__APP_VERSION__) {
    for (const el of document.querySelectorAll("[data-app-version]")) {
      el.textContent = `v${window.__APP_VERSION__}`;
    }
  }

  // Startup loading overlay (the #loading element, visible by default): a progress
  // bar over the canvas so a slow first load shows feedback. Fetch fills the first
  // ~half of the bar, SDF meshing the rest (see below); done() fades it out.
  const loading = createLoadingScreen();
  loading.setProgress(0.02, t("loading.data"));

  // Sources & provenance popup: wire it + fill its static parts (intro + grade
  // key) now; its coverage tally needs the loaded dataset, so it is filled in
  // below once data arrives. It is NOT shown on launch (a visitor just watches
  // the loading bar + its tagline); it opens on demand from the Sources button,
  // the Legend/About "Sources & provenance" links, and the guided tour.
  const sourcingModal = wireSourcingModal();
  buildAboutSourcing(null);

  let data;
  try {
    data = await loadBrainData("data", (p) => {
      // Fill the sourcing popup's coverage bars as soon as meta lands (before the
      // slow shape/mesh phase), so the tally is ready the instant a visitor opens
      // the popup on demand, not just the intro text.
      if (p.stage === "meta-ready" && p.meta?.provenance_stats) {
        buildAboutSourcing({ provenanceStats: p.meta.provenance_stats });
      }
      if (p.stage === "shapes" && p.total) {
        loading.setProgress(
          0.05 + 0.45 * (p.loaded / p.total),
          t("loading.shapes", { done: p.loaded, total: p.total }),
        );
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
  // One job per DISTINCT spec, not per structure: a symmetric structure's two
  // hemispheres share one shape file (js/data.js dedupes the fetch, so the twins
  // hold the very same spec object), and the left is the right's geometry flipped
  // by `mirrorGeometryX`, not a different solid. Meshing both sides re-ran an
  // identical marching-cubes pass for 20 of the 46 structures: 44% of the field
  // samples at load, spent to produce a duplicate. The twin gets a `clone()`
  // below, since `buildStructureMesh` mirrors in place.
  const sdfBySpec = new Map(); // spec object -> the id that carries its geometry
  const sdfItems = [];
  for (const s of data.structures) {
    if (!s.shape || s.shape.type !== "sdf") continue;
    if (sdfBySpec.has(s.shape)) continue;
    sdfBySpec.set(s.shape, s.id);
    sdfItems.push({ id: s.id, spec: s.shape, shapeFile: s.shape_file });
  }

  // Baked geometry first (tools/bake_meshes.mjs): downloading the meshes replaces
  // ~3.8s of worker meshing with a decode of a few tens of ms, and the download is
  // paid once (sw.js then revalidates it to a bodyless 304) where the meshing was
  // paid on every single load. Whatever the bake does not cover falls through to
  // the runtime mesher below, so a tree that was never baked still runs.
  const sdfGeoms = new Map();
  const baked = await loadBakedMeshes("data", ({ loaded, total }) => {
    loading.setProgress(0.5 + 0.4 * (total ? loaded / total : 1),
      t("loading.geometry", { done: loaded, total }));
  });
  const toMesh = [];
  for (const item of sdfItems) {
    const mesh = baked.get(item.shapeFile);
    if (mesh) sdfGeoms.set(item.id, geometryFromArrays(mesh.positions, mesh.indices));
    else toMesh.push(item);
  }

  // Runtime meshing, for whatever the bake did not supply. On a fully baked build
  // this list is empty and neither the worker pool nor the quality budget is ever
  // constructed; it is the fallback path, not the normal one.
  if (toMesh.length) {
    if (toMesh.length !== sdfItems.length) {
      console.info(`baked meshes: ${toMesh.length} of ${sdfItems.length} structure(s) ` +
        "missing from the bake; meshing those in the browser");
    }
    const pool = createSdfPool();
    // Mesh cheapest-first under a wall-time budget: the small nuclei double as a
    // throughput probe, and if the machine turns out to be too slow to finish the
    // heavy lobes at authored resolution, the budget coarsens the ones still
    // queued (see js/sdf-quality.js). Measured, never sniffed from the user agent.
    const budget = createMeshBudget();
    try {
      const meshed = await pool.meshAll(
        budget.order(toMesh),
        ({ id, done, total, frac }) => {
          budget.note(frac); // feed the throughput measurement back to the budget
          // `frac` is cost-weighted and includes the in-flight structures' own
          // progress, so on a slow phone the bar keeps moving through a single
          // heavy mesh; the "(n/total)" counter says how far along the batch is,
          // so a long pause still reads as progress rather than a freeze.
          const name = data.byId.get(id)?.base_name || id;
          loading.setProgress(0.5 + 0.45 * frac, t("loading.meshing", { name, done, total }));
          if (budget.degraded) loading.notice(t("loading.reducedQuality"));
        },
        budget.adjust,
      );
      for (const [id, geom] of meshed) sdfGeoms.set(id, geom);
    } catch (err) {
      console.warn("sdf pool meshing failed; falling back to synchronous", err);
    } finally {
      pool.dispose(); // geometry is built once at load; free the workers after
    }
  }

  // Build region meshes and index them for the arrows. SDF structures get their
  // pre-meshed geometry; everything else is meshed synchronously inside the call.
  const meshes = [];
  const meshById = new Map();
  const geomUsed = new Set();
  for (const structure of data.structures) {
    // Resolve through the spec, so a mirrored twin picks up the geometry meshed
    // under its right-side partner's id. Every consumer after the first gets a
    // clone: `buildStructureMesh` mirrors (and so mutates) what it is handed, and
    // a clone is a memcpy against a million-sample re-mesh.
    let geom = sdfGeoms.get(sdfBySpec.get(structure.shape) ?? structure.id);
    if (geom) {
      if (geomUsed.has(geom)) geom = geom.clone();
      else geomUsed.add(geom);
    }
    const mesh = buildStructureMesh(structure, geom);
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
  const isolateGroupFor = (mesh) => {
    const base = stripSide(mesh.userData.structure.id);
    return meshes.filter((m) => stripSide(m.userData.structure.id) === base);
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
      if (isPickableMesh(hit.object)) return hit;
    }
    return null;
  };
  // Just the nearest visible structure mesh (hover + double-click only need that).
  const pickAt = (clientX, clientY) => pickStructureHit(clientX, clientY)?.object || null;

  // Connection info panel (populated when an arrow is clicked or a connection is
  // picked in the search). Created here so the click/tap handlers below can use it.
  const tabs = createPanelTabs();
  // The URL fragment <-> UI registry (js/url-state.js). Created before anything that
  // owns a piece of UI state, since each control registers its own {read, write} pair
  // as it is wired; the fragment is assembled + applied at the end of main().
  const urlState = createUrlState();
  // Any strip change (open / close / activate / drag-reorder) is part of what a link
  // reproduces, so mirror the whole strip, not just the active tab.
  tabs.setOnChange(() => urlState.sync());
  const info = createInfoPanel(data, sourcingModal);
  // Open (or re-activate) a detail tab for the thing a select* just rendered +
  // focused; the reopen thunk re-runs that select* so clicking the tab restores
  // the panel + the 3D focus. Kept here (not in createInfoPanel) so the tab's key
  // and how to re-focus the scene live with the select* layer.
  const openDetailTab = (key, title, reopen) => {
    // The single choke point every node focus (drug / receptor / target / structure /
    // connection / circuit / group) passes through, so emit one semantic analytics
    // event here (the `key` is already `<kind>:<id>`) instead of at each call site.
    // No-op unless umami is loaded (see js/app-init.js window.trackEvent).
    window.trackEvent?.("focus", { node: key });
    return tabs.openDetail({ key, title, reopen });
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
  // Last tab closed: drop the 3D focus and, since a panel-only focus (enzyme,
  // effect) has no 3D state for selection.clear() to unwind, its row highlight too.
  const panelOnlyFocuses = []; // their reset()s, see createPanelOnlyFocus
  const clearNodeFocus = () => {
    selection.clear();
    for (const reset of panelOnlyFocuses) reset();
  };
  tabs.setOnEmpty(clearNodeFocus);
  // Stepping back to the Settings tab is "put the scene back": the detail tabs stay
  // in the strip as history, but whatever they lit (a drug's animation, a circuit
  // pulse, an isolate) stops, so the controls are never read over a live overlay.
  // Clicking the tab again re-applies its focus (its reopen thunk).
  tabs.setOnSettings(clearNodeFocus);

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
  const meshesOfIds = (ids) => ids.map((id) => meshById.get(id)).filter(Boolean);
  // The shared shape of every focus that lights the scene (target, drug, circuit,
  // projection group): `apply` sets the dim/pins + starts its animation and returns
  // the focused mesh set; a hover `preview` stops there (no panel/tab/spread).
  // Otherwise: spread a deep focus apart, render the panel, frame the set when
  // `frame` (a search / panel pick; a legend row leaves the view where it is), light
  // its legend row and open its tab, whose reopen thunk re-runs the focus. `watch`
  // (an animation controller) drops the row highlight the moment the focus stops
  // being exactly that region set; `buildLegend(toggle)` returns the row reflector.
  const createSceneFocus = ({ kind, apply, show, title, watch = null, buildLegend = null }) => {
    let activeId = null;
    let reflect = () => {};
    const go = (item, opts = {}) => {
      const { frame = false, preview = false } = opts;
      const meshSet = apply(item);
      if (preview) return;
      autoSpreadIfDeep(meshSet);
      show(item, opts);
      if (frame && meshSet.length) focus.focusMeshes(meshSet);
      activeId = item.id;
      reflect(activeId);
      openDetailTab(`${kind}:${item.id}`, title(item), () => go(item));
    };
    const toggle = (item) => {
      if (activeId === item.id) selection.clear(); // the watcher hides the animation
      else go(item);
    };
    if (watch) {
      selection.onIsolate((isolated) => {
        if (watch.active && !watch.matches(isolated)) {
          watch.hide();
          activeId = null;
          reflect(activeId);
        }
      });
    }
    if (buildLegend) reflect = buildLegend(toggle);
    return go;
  };
  const focusTarget = createSceneFocus({
    kind: "target",
    apply: (tgt) => {
      const meshSet = meshesOfIds(tgt.structureIds);
      selection.setCircuit(meshSet, []);
      receptorMarkers.show(meshSet, tgt.swatchColor);
      return meshSet;
    },
    // Framing from the search box covers the whole brain for a ubiquitous receptor.
    show: (tgt) => (tgt.kind === "receptor" ? info.showReceptor(tgt.receptor) : info.showTarget(tgt)),
    title: (tgt) => tgt.name,
    watch: receptorMarkers,
    buildLegend: (toggle) => buildTargetLegend(data, toggle),
  });
  // Picking a target in the search box always focuses it (and frames it), never
  // toggles it off, the same way a structure/connection search result behaves.
  const selectTarget = (tgt) => focusTarget(tgt, { frame: true });

  // Enzyme focus (the Enzymes section + a drug panel's Metabolism row). Unlike every
  // other focus in this file it touches NOTHING in the 3D scene: a metabolic enzyme
  // is pharmacokinetics with no anatomy, so there is no mesh set to dim, no dots and
  // no arrows to pin. It is a panel + tab only, and the section caption says so, so
  // the still scene reads as intended rather than as a broken click.
  //
  // A panel-only focus (an enzyme, an effect): a panel + tab with no 3D state of its
  // own, which is exactly why it has to drop the PREVIOUS focus by hand: every other
  // focus replaces the scene as it applies itself, so stepping from a drug tab to an
  // enzyme tab would otherwise leave the drug's dots, wash and flow beads running
  // under a panel that no longer mentions that drug (the watcher below hides them off
  // this clear). Folding the whole panel away is not a focus change and deliberately
  // keeps it going. Its legend row stays lit only while it is what is focused: any
  // focus that DOES touch the scene puts it out (the onIsolate mirror; focus() clears
  // first and sets the active id after, so it fires on the way in and leaves the
  // incoming row lit). Returns {focus, reset}; reset is for clearNodeFocus.
  const createPanelOnlyFocus = ({ kind, show, buildLegend }) => {
    let activeId = null;
    let reflect = () => {};
    const focus = (item) => {
      selection.clear();
      show(item);
      activeId = item.id;
      reflect(activeId);
      openDetailTab(`${kind}:${item.id}`, item.label, () => focus(item));
    };
    const reset = () => {
      if (activeId === null) return;
      activeId = null;
      reflect(null);
    };
    const toggle = (item) => {
      if (activeId !== item.id) { focus(item); return; }
      reset();
      tabs.close(`${kind}:${item.id}`);
    };
    selection.onIsolate(reset);
    reflect = buildLegend(toggle);
    panelOnlyFocuses.push(reset);
    return focus;
  };
  const focusEnzyme = createPanelOnlyFocus({ kind: "enzyme",
    show: (enz) => info.showEnzyme(enz), buildLegend: (onPick) => buildEnzymeLegend(data, onPick) });
  info.onEnzyme(focusEnzyme);
  // The Effects section (BETA): the same panel + tab shape.
  const focusEffect = createPanelOnlyFocus({ kind: "effect",
    show: (effect) => info.showEffect(effect),
    buildLegend: (onPick) => buildEffectLegend(data, onPick) });
  info.onEffect(focusEffect);

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
  // The arrows of a drug's mapped projection kinds: its target transmitter systems
  // (`flowKinds`, the set the flow overlay rides) or its *context* systems
  // (`contextKinds`, postsynaptic-receptor pathways pinned statically, dimmed, no
  // beads, so a purely postsynaptic agent such as an antihistamine blocking H1 still
  // visibly engages its system's fan without the flow overlay's tone claim). Empty
  // when the drug has no mapped system, so the overlay is simply absent for it.
  const arrowsOfKinds = (kindList) => {
    const kinds = new Set(kindList || []);
    return kinds.size ? arrows.filter((a) => kinds.has(a.projection.kind)) : [];
  };
  const focusDrug = createSceneFocus({
    kind: "drug",
    apply: (drug) => {
      const meshSet = meshesOfIds(drug.structureIds);
      const flowArrows = arrowsOfKinds(drug.flowKinds);
      selection.setCircuit(meshSet, flowArrows, arrowsOfKinds(drug.contextKinds));
      drugAnim.show(drug, meshById);
      // Per-kind flow direction/weight (js/data.js flowSystems): the pulse rides
      // "up" the fan when the drug raises that system's tone, damped "down" when it
      // lowers it, its intensity scaled by the drug's affinity on that system.
      circuitAnim.play(flowArrows, drug.flowSystems || {}); // no-op for a drug with no mapped pathways
      return meshSet;
    },
    // highlightMetabolite / highlightEnzymes: pass-through "why did this open" hints
    // for the panel (see info.showDrug), not focus state.
    show: (drug, { highlightMetabolite = null, highlightEnzymes = null }) =>
      info.showDrug(drug, { highlightMetabolite, highlightEnzymes }),
    title: (drug) => drug.displayName,
    watch: drugAnim,
    buildLegend: (toggle) => buildDrugLegend(data, toggle),
  });
  const selectDrug = (drug, opts = {}) => focusDrug(drug, { frame: true, ...opts });
  // The Drugs section's two list controls. Registered here (once) rather than inside
  // buildDrugLegend, which re-runs on a language switch: the inputs are static markup,
  // so one registration covers every rebuild. Each write drives the input's own event,
  // so the live filter + the persisted metabolite preference behave as if typed/clicked.
  const drugsFilter = document.getElementById("drugs-filter");
  const metabToggle = document.getElementById("drugs-show-metabolites");
  if (drugsFilter) {
    urlState.register("drugq", {
      read: () => drugsFilter.value || null,
      write: (v) => { drugsFilter.value = v; drugsFilter.dispatchEvent(new Event("input")); },
    });
    drugsFilter.addEventListener("input", () => urlState.sync(TYPING_SETTLE_MS));
  }
  if (metabToggle) {
    urlState.register("metab", {
      read: () => (metabToggle.checked ? null : "0"),
      write: (v) => {
        const on = v !== "0";
        if (metabToggle.checked === on) return;
        metabToggle.checked = on;
        metabToggle.dispatchEvent(new Event("change"));
      },
    });
    metabToggle.addEventListener("change", () => urlState.sync());
  }

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

  const { tourOnScreen } = wireCanvasPicking({
    arrows, canvas, labels, meshes, pickStructureHit, raycaster,
    selectConnection: (...a) => selectConnection(...a), selection,
    selectStructure: (...a) => selectStructure(...a), setPointer, tabs,
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
  const seeThrough = createSeeInside({ meshes, camera, controls });

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

  // Clicking a "Neurotransmitter tone" row in a drug panel focuses that projection
  // group (isolates its arrows + opens its tab), exactly like its Projections legend
  // row, so you can go from a drug to the pathway system it engages.
  info.onProjectionGroup((group) => focusProjectionGroup(group, { frame: true }));

  canvas.addEventListener("dblclick", (event) => {
    if (tourOnScreen()) return; // brain interactions are inert during the tour
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
  const arrowsAmong = (meshSet) =>
    arrows.filter((a) => meshSet.has(a.fromMesh) && meshSet.has(a.toMesh));
  const focusCircuit = createSceneFocus({
    kind: "circuit",
    apply: (circuit) => {
      const cMeshes = meshesOfIds(circuit.structures);
      const cArrows = arrowsAmong(new Set(cMeshes));
      selection.setCircuit(cMeshes, cArrows);
      circuitAnim.play(cArrows);
      return cMeshes;
    },
    show: (circuit) => info.showCircuit(circuit),
    title: (circuit) => circuit.name,
  });
  // The (established) arrows this projection group stands for: by sign in sign
  // mode, by kind otherwise (the data record is per kind/sign). Tentative arrows
  // are excluded, matching the established-only legend rows.
  const groupArrowsOf = (group) => arrows.filter((a) =>
    !a.tentative
    && (group.mode === "sign" ? a.projection.sign === group.key
                              : a.projection.kind === group.key));
  const focusProjectionGroup = createSceneFocus({
    kind: "group",
    apply: (group) => {
      const gArrows = groupArrowsOf(group);
      const gMeshes = [...new Set(gArrows.flatMap((a) => [a.fromMesh, a.toMesh]))];
      selection.setCircuit(gMeshes, gArrows); // pin the arrows, no pulse
      return gMeshes;
    },
    show: (group) => info.showProjectionGroup(group),
    title: (group) => group.name,
  });

  const rebuildLegend = () => {
    reflectLegend = buildLegend(
      data, meshById, arrows, selection, projVis, circuitAnim, signColorMode,
      // Opening the picked structure's tab (no reframe: keep the legend pick's
      // current camera, just add the detail tab + halo, like the isolate already
      // does in the viewer).
      (mesh) => selectStructure(mesh),
      // Circuit / projection-group row picks: isolate + open the sourced detail
      // panel + tab, exactly like a drug / target row.
      focusCircuit, focusProjectionGroup,
      // The Projections section hosts an addon slot; the hook lives on the info panel.
      info.appendAddons);
    selection.refresh(); // re-grey the fresh rows for the current isolate state
  };
  rebuildLegend();
  // The static colour key (Legend section) is built once: it shows the scene's
  // encodings (gem-dot signs, drug effect colours, dotted = speculative) from the
  // meta maps and doesn't depend on the arrow colour mode.
  buildLegendKey(data);
  // Fill the About panel's "Sources & provenance" block (grade key + the programmatic
  // coverage tally) from the dataset's meta. `nav` lets an expanded kind's example node
  // jump to the real entity: each callback closes the popup first so the focus is
  // visible behind it, then focuses the drug / target / structure / circuit / group.
  // One nav for every node row: the Data browser's rows, and (each wrapped to close
  // the popup first, so the focus is visible behind it) the Sources popup's examples.
  // A projection row isolates the arrow that carries it.
  const nodeNav = {
    drug: (d, opts) => focusDrug(d, { frame: true, ...opts }),
    target: (tg) => focusTarget(tg, { frame: true }),
    structure: (id) => {
      const mesh = meshById.get(id);
      if (mesh) selectStructure(mesh, { frame: true });
    },
    connection: (proj) => {
      const arrow = arrows.find((a) => a.projection === proj);
      if (arrow) selectConnection(arrow, { frame: true, isolate: true });
    },
    circuit: (c) => focusCircuit(c, { frame: true }),
    group: (g) => focusProjectionGroup(g, { frame: true }),
  };
  const sourcingNav = {
    ...Object.fromEntries(Object.entries(nodeNav).map(([k, go]) => [k, (...args) => {
      sourcingModal.close();
      go(...args);
    }])),
    // Not an example node but the whole list: the popup's "Open the Data browser"
    // line. Reads `showNodeBrowser` at call time, since it is only assigned below.
    browser: () => { sourcingModal.close(); showNodeBrowser(); },
  };
  buildAboutSourcing(data.meta, { data, nav: sourcingNav });

  // The Data browser: the same nodes the tally counts, listed one by one. It opens
  // as a **detail tab** rather than expanding in the accordion, because thousands of
  // rows want the whole pane; its DOM is a detached container the browser owns, so
  // the filter text, the selects and the scroll position all survive a tab switch
  // (the panel only hosts it, see info.showNodeBrowser).
  // Its nav is `nodeNav` above (a browser row is already in the open panel, so no
  // popup to close).
  // Its tab key. Unlike every other detail tab this one identifies a *view*, not a
  // node, so it carries no id; the deep-link layer maps it to `#browser=1`.
  const NODES_TAB_KEY = "browser:1";
  // Open (or re-activate) the Data browser tab. Assigned just below; a no-op if the
  // section's markup is missing, so the deep link + the row can call it blind.
  let showNodeBrowser = () => {};
  const nodesToggle = document.getElementById("nodes-toggle");
  if (nodesToggle) {
    const nodesBody = document.createElement("div");
    nodesBody.id = "nodes-body";
    const nodeBrowser = createNodeBrowser({
      body: nodesBody,
      data,
      deps: {
        t,
        formatHalfLife,
        nav: nodeNav,
      },
      ui: {
        pill: info.provenancePill,
        fold: foldText,
        kindLabel: (k) => t(KIND_LABELS[k] || k),
        gradeLabel: (g) => t(GRADE_LABELS[g] || g),
        // The downloadable-file list already lives in the About popup; point at it
        // rather than shipping a second copy of the same links. (Late-bound: the
        // About modal is wired further down in main().)
        openDataFiles: () => aboutModal.openDataFiles(),
      },
    });
    // Lazy: collecting every node walks the whole dataset, so building waits for the
    // first open rather than running at boot; reopening is then just a re-host.
    showNodeBrowser = () => {
      nodeBrowser.open();
      info.showNodeBrowser(nodesBody);
      openDetailTab(NODES_TAB_KEY, t("panel.nodes"), showNodeBrowser);
    };
    // The rows are a wide table and read nothing off the scene, so the browser opens
    // maximized (this visit only, see setNo3d's `persist`).
    nodesToggle.addEventListener("click", () => {
      setNo3d(true, { persist: false });
      showNodeBrowser();
    });
  }

  // Simulation (beta): the same detail-tab shape as the Data browser above (a view,
  // not a node, so its key carries no id and the deep-link layer maps it to
  // `#simulation=1`), and the same detached container, since the picked drugs and the
  // solver's wish list are state a tab switch must not throw away. The drug list
  // itself rides the URL under `sim`, registered further down with the other views.
  const SIM_TAB_KEY = "simulation:1";
  let showSimulation = () => {};
  let simulation = null;
  const simToggle = document.getElementById("simulation-toggle");
  if (simToggle) {
    const simBody = document.createElement("div");
    simBody.id = "simulation-body";
    simulation = createSimulation({
      body: simBody,
      data,
      deps: { t, nav: { drug: (d) => focusDrug(d, { frame: true }) } },
      ui: { fold: foldText },
    });
    simulation.setOnChange(() => urlState.sync(200));
    showSimulation = () => {
      simulation.open();
      info.showSimulation(simBody);
      openDetailTab(SIM_TAB_KEY, t("panel.simulation"), showSimulation);
    };
    // Two plots and a solver want the whole pane, and none of it lights the scene
    // (it is pharmacology, not anatomy), so the tab opens maximized for this visit.
    simToggle.addEventListener("click", () => {
      setNo3d(true, { persist: false });
      showSimulation();
    });
  }

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
    b.addEventListener("click", () => { setColorMode(b.dataset.mode === "sign"); urlState.sync(); });
  }
  // `colors=sign`: which key the arrows are coloured by (transmitter is the default).
  urlState.register("colors", {
    read: () => (signColorMode ? "sign" : null),
    write: (v) => setColorMode(v === "sign"),
    reset: () => setColorMode(false),
  });

  const { autoSpread, autoSpreadIfDeep, arrowRetrim, expandPanel } = wireControls(
    { camera, controls, meshes, arrows, labels, focus, selection, projVis, seeThrough, urlState });
  // Hold arrows a constant apparent width as the camera zooms (advanced by its
  // tick() in the render loop, like arrowRetrim).
  const arrowWidth = createArrowWidth({ arrows, camera, controls, focus });
  const toolbar = wireToolbar({ focus, meshes, arrows, data, selection, tabs, urlState, expandPanel, selectStructure, selectConnection, focusTarget, focusDrug, focusEnzyme, focusEffect, focusCircuit, focusProjectionGroup });
  // A drug panel's clickable Class / Nomenclature opens search with a structured
  // filter (class:"..." / nbn:"...") so you can pivot to the whole class.
  info.onSearch(toolbar.openSearchWithQuery);
  // Clicking a structure illustration / molecule diagram in a panel enlarges it.
  const lightbox = wireImageLightbox();
  info.onImage((src, alt, opts) => lightbox.open(src, alt, opts));
  const shortcutsHelp = wireShortcutsHelp(); // the "?" / keyboard-button popup
  // sourcingModal was created early (wired above, opens on demand); the Legend + About
  // popups link to it via their "Sources & provenance" rows.
  const legendModal = wireLegendModal(sourcingModal); // toolbar legend button / k key
  // "What's new": auto-opens once after an update (below, after the intro settles)
  // and from the About popup's link. Its notes are fetched only when it opens.
  const changelog = createChangelog({
    version: String(window.__APP_VERSION__ || ""),
    sourceUrl: (window.__APP_CONFIG__ || {}).sourceUrl,
    t, pick: window.__I18N__.pick, wireModal,
  });
  const aboutModal = wireAboutModal(sourcingModal, changelog); // the toolbar info-button popup
  wireShortcuts(shortcutsHelp, tabs, selection, lightbox, aboutModal, legendModal, sourcingModal, changelog); // single-key shortcuts (n/s/l/p/k/c/r/m/f/?/Esc) + Tab cycles detail tabs
  projVis.apply(); // established arrows visible, tentative ones start hidden
  // Honor screenshot/deep-link view params (?only=, ?view=, ?explode=, ...).
  applyViewParams({ scene, camera, controls, meshes, arrows, labels, urlState });
  // Scene is built: fill the loading bar. The overlay's dismissal is coupled to
  // the intro launch further below (an interactive load waits for the visitor to
  // click "Start exploring"; an automated view drops it at once), so the brain is
  // revealed just as the assemble intro begins.
  loading.setProgress(1, t("loading.building"));
  console.log(
    `Loaded ${meshes.length} structures and ${arrows.length} projections.`,
  );

  const {
    tour, tourEl,
  } = createViewerTour({
    arrows, autoSpread, controls, data, focus, focusDrug,
    focusProjectionGroup, focusTarget, legendModal, meshById, meshes, NODES_TAB_KEY,
    selection, selectStructure, setNo3d: (...a) => setNo3d(...a),
    showNodeBrowser: (...a) => showNodeBrowser(...a), sourcingModal, tabs, toolbar,
  });
  // Auto-start only on a genuinely fresh view: not a screenshot / deep-link mode,
  // and nothing already focused (a hash deep link, or a click during the intro).
  const tourEligible = () =>
    !AUTOMATED_VIEW && !tabs.activeKey() && !selection.getSelected();
  // Replay from the About popup (close it first so the tour isn't behind it).
  tourEl("about-tour")?.addEventListener("click", () => {
    aboutModal.close();
    tour.start();
  });
  // Auto-start waits for the assemble intro to settle, and declines to stack on an
  // open popup (Sources, or the "What's new" notes that now open at launch): the
  // Sources one no longer opens on launch, but a visitor could open it manually
  // during the intro, so if either is up we defer and the observer retries the moment
  // it closes. (Mid-tour the observer is a no-op: maybeAutoStart/start bail when the
  // tour is already active, so the sourcing open / close steps can't restart it.)
  // Two gates, not one. `sceneSettled` means the launch is over however it ended;
  // `introCompleted` means the assemble reached its natural end, which the tour
  // requires so it never starts over a user's own action.
  let sceneSettled = false;
  let introCompleted = false;
  let tourForcedStarted = false; // one-shot guard for the ?tour=1 forced start
  const tourGateEls = ["sourcing-modal", "changelog-modal"].map(tourEl).filter(Boolean);
  const tourGateOpen = () => tourGateEls.some((el) => !el.hidden);
  const tryAutoTour = () => {
    if (!sceneSettled || tourGateOpen()) return;
    if (TOUR_FORCED) {
      // Forced: ignore the seen gate + eligibility, but never re-trigger.
      if (!tourForcedStarted) { tourForcedStarted = true; tour.start(); }
    } else if (introCompleted) {
      tour.maybeAutoStart(tourEligible());
    }
  };
  /** The launch is over; `completed` says the assemble reached its natural end. */
  const settleScene = (completed) => {
    sceneSettled = true;
    if (completed) introCompleted = true;
    tryAutoTour();
  };
  for (const el of tourGateEls) {
    new MutationObserver(tryAutoTour)
      .observe(el, { attributes: true, attributeFilter: ["hidden"] });
  }
  /**
   * "What's new" at LAUNCH, not at settle: release notes are about the build, not
   * about the scene, so a returning visitor reads them the moment they click through
   * the overlay rather than several seconds later once the assemble has finished.
   * (It used to ride the tour's settle gate, which is what made it wait, and which
   * also lost it entirely on a load where the intro was cancelled.) Fire-and-forget
   * and one-shot: it decides for itself whether there is anything to show, and the
   * tour gates on its popup above so the two never stack.
   */
  let changelogTried = false;
  const showChangelogOnce = () => {
    if (changelogTried) return;
    changelogTried = true;
    changelog.showIfUnseen();
  };

  // Auto-play the "assemble" intro on a plain load. Grabbing the explode slider
  // cancels it so a manual drag wins. Skipped when ?explode= is pinned (deep
  // links / headless screenshots) so the requested static amount is honored.
  const explodeSlider = document.getElementById("explode");
  const intro = createIntroAnimation(
    { meshes, arrows, slider: explodeSlider, camera, controls, focus,
      // The assemble re-fits the arrows in `fast` mode, so it borrows the same
      // deferred precise re-trim the manual spread uses.
      retrim: arrowRetrim,
      // Once the assemble settles, offer the tour (once per visitor, and not while
      // the Sources popup is open: see tryAutoTour). Fires on a cancel too, with
      // completed=false, which settles the scene without earning the tour.
      onSettle: settleScene });
  explodeSlider.addEventListener("input", () => intro.cancel());
  // The launch (assemble intro, or an instant settle when animations are off) is
  // wrapped so it can fire exactly when the loading overlay is dismissed below.
  const beginScene = () => {
    if (!HAS_EXPLODE) {
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
      if (animSettings.enabled) {
        intro.start();
      } else {
        applyExplode(meshes, 0, arrows);
        // No assemble intro to finish (so onSettle never fires); settle after a short
        // beat. It counts as completed: there was no animation for the user to cut
        // short, so the tour is as welcome here as after a full assemble.
        setTimeout(() => settleScene(true), 500);
      }
    } else if (TOUR_FORCED) {
      // ?explode= pinned: the intro block above is skipped, so onSettle never fires.
      // A forced tour still wants to run, so settle the gate condition after a beat.
      setTimeout(() => settleScene(false), 500);
    }
  };
  // Dismiss the loading overlay, coupled to the launch. An automated view (headless
  // ui=0, or an ?explode= deep-link / screenshot) drops it at once so a capture is
  // never trapped behind the overlay; a normal interactive load keeps it up showing
  // the "Start exploring" button (so the tagline + invite can be read) and launches
  // on the click, the assemble intro playing as the overlay fades.
  if (AUTOMATED_VIEW) {
    // An automated view (headless capture, deep-link screenshot) is not a visit, so it
    // launches with no release notes over the shot.
    loading.done();
    beginScene();
  } else {
    loading.waitForStart().then(() => {
      beginScene();
      showChangelogOnce();
    });
  }

  wireUrlBindings({
    aboutModal, arrows, changelog, data, focusCircuit, focusDrug,
    focusEffect, focusEnzyme, focusProjectionGroup, focusTarget, legendModal, meshes,
    selectConnection, selectStructure, shortcutsHelp,
    showNodeBrowser: (...a) => showNodeBrowser(...a),
    showSimulation: (...a) => showSimulation(...a),
    simulation, sourcingModal, tabs, urlState,
  });

  // Apply the incoming URL (after the intro exists, so a focused node cancels the
  // assemble intro rather than fighting its explode tween), then keep the address bar
  // mirroring the UI: copying it is just selecting the URL bar, no dedicated button.
  // The sync also normalizes a legacy / hand-written link into the canonical fragment.
  if (urlState.applyHash()) intro.cancel();
  urlState.sync();
  urlState.start();

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
  // Hand the render loop to everything wired before it existed (the theme's scene
  // repaint); see the `repaint` hook in scene/setup.js.
  setRepaint(invalidate);
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

  const updateSpeedRow = wireSpeedSlider({ invalidate, urlState,
    animating: () => drugAnim.active || receptorMarkers.active || circuitAnim.active });

  // Panel header toggles: day/night + the panel-only "reading" mode.
  const { no3dOn, setNo3d } = wireHeaderToggles({ theme, expandPanel, invalidate, intro, urlState });

  // A framing tween (focusing a node, recentering, the explode re-aim) moves the
  // camera over several frames, so the URL's `cam` is only right once it settles:
  // record it on the tween's falling edge rather than per frame.
  let camWasMoving = false;

  renderer.setAnimationLoop(() => {
    // Panel-only mode: the scene (canvas + label overlay) is display:none, so skip
    // the ticks and the render entirely. Animations freeze in place and resume when
    // 3D returns, repainted by setNo3d's invalidate().
    if (no3dOn()) return;
    // Advance the intro + any focus/recenter tween before controls.update()
    // reads the target + camera position for this frame. Each tick() returns
    // whether it animated this frame; controls.update() returns whether the
    // camera moved (damping / auto-rotate). Any true keeps us rendering.
    let active = false;
    if (intro.tick()) active = true;
    if (autoSpread.tick()) active = true;
    if (arrowRetrim.tick()) active = true;
    const camMoving = focus.tick();
    if (camMoving) active = true;
    else if (camWasMoving) urlState.sync(); // tween done: the settled view is the link's
    camWasMoving = camMoving;
    if (circuitAnim.tick()) active = true;
    if (receptorMarkers.tick()) active = true;
    if (drugAnim.tick()) active = true;
    if (controls.update()) active = true;
    // After controls.update() so it reads this frame's settled camera distance.
    if (arrowWidth.tick()) active = true;
    // After controls.update() so the fade reads this frame's camera + target.
    if (seeThrough.tick()) active = true;
    if (active) needsRender = true;
    const rendered = needsRender;
    // Adaptive quality watches the frame time of actually-rendered animated frames
    // and may step the pixel ratio down/up; a level change forces one more repaint.
    if (adaptive.tick(rendered && active)) needsRender = true;
    if (!needsRender) return; // idle: skip the render + label passes this frame
    needsRender = false;
    // Reveal/hide the speed slider from the live animation state. Cheap + guarded to a
    // no-op when unchanged; a stop always triggers one final render here, so it can't
    // stay stuck visible after the focus clears.
    updateSpeedRow();
    renderer.render(scene, camera);
    // CSS2D labels render as a separate DOM pass after the WebGL frame.
    labels.render(scene, camera);
  });
}

main();
