// The focus layer: every way content gets focused (a structure, a connection, a
// receptor/target, a drug, a circuit, a projection group, and the panel-only enzyme /
// effect) funnels through the helpers built here, so the dim + animation + panel +
// tab + frame sequence lives in one place. Also wires the detail panel's cross-links
// (a row in one panel focusing another node) and the Drugs list's two URL keys.

import { createCircuitAnimation } from "../circuit-anim.js";
import { createReceptorMarkers } from "../receptor-markers.js";
import { createDrugAnimation } from "../drug-anim.js";
import { buildEffectLegend, buildEnzymeLegend } from "../legend/browse.js";
import { buildTargetLegend } from "../legend/targets.js";
import { buildDrugLegend } from "../legend/drugs.js";
import { TYPING_SETTLE_MS } from "./toolbar.js";

const { t } = window.__I18N__;

/**
 * @param {{arrows: object[], autoSpreadIfDeep: Function, data: object, focus: object,
 *          info: object, isolateGroupFor: Function, meshById: Map, openDetailTab: Function,
 *          scene: object, selection: object, tabs: object, urlState: object}} deps
 *   `focus` is the camera focus (scene/camera.js createCameraFocus)
 * @returns {object} the focus / select functions plus the three animation controllers
 */
export function wireFocus({
  arrows, autoSpreadIfDeep, data, focus, info, isolateGroupFor, meshById, openDetailTab,
  scene, selection, tabs, urlState,
}) {
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

  // Clicking a "Pharmacodynamics: net neurotransmission" row in a drug panel focuses that projection
  // group (isolates its arrows + opens its tab), exactly like its Projections legend
  // row, so you can go from a drug to the pathway system it engages.
  info.onProjectionGroup((group) => focusProjectionGroup(group, { frame: true }));

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

  return {
    circuitAnim, drugAnim, receptorMarkers,
    focusCircuit, focusDrug, focusEffect, focusEnzyme, focusProjectionGroup, focusTarget,
    selectConnection, selectDrug, selectStructure, selectTarget,
  };
}
