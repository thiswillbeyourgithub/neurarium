// Entry point: builds the three.js scene from the dataset and hands it to the boot
// modules, in order: meshing (boot/meshing.js), focus (boot/focus.js), picking,
// legends, view tabs (boot/views.js), controls + toolbar + popups, the launch
// (boot/launch.js: tour, intro, changelog), the URL bindings, and the on-demand
// render loop (boot/render-loop.js). Each gets its dependencies as one object; an
// owner wired later than its consumer is handed over late-bound, `(...a) => f(...a)`.
//
// OrbitControls already gives us the requested touch gestures for free:
// one finger = rotate, two fingers = pinch-zoom + pan.

import { loadBrainData } from "./data.js";
import { createLoadingScreen } from "./loading.js";
import { buildArrows } from "./arrows.js";
import { createLabels } from "./labels.js";
import { createChangelog } from "./changelog.js";
import { createUrlState } from "./url-state.js";
import { stripSide } from "./util.js";
import { createProjectionVisibility } from "./legend/anatomy.js";
import { createPanelTabs } from "./panel/tabs.js";
import { initThree } from "./scene/setup.js";
import { createArrowWidth } from "./scene/explode.js";
import { createSeeInside } from "./scene/see-inside.js";
import { createSelection } from "./scene/selection.js";
import { applyViewParams, createCameraFocus } from "./scene/camera.js";
import {
  wireAboutModal, wireImageLightbox, wireLegendModal, wireModal, wireShortcutsHelp,
  wireSourcingModal,
} from "./about/modals.js";
import { buildAboutSourcing } from "./about/sourcing.js";
import { createInfoPanel } from "./panel/info.js";
import { wireControls } from "./boot/controls.js";
import { wireToolbar } from "./boot/toolbar.js";
import { wireShortcuts } from "./boot/shortcuts.js";
import { wireUrlBindings } from "./boot/url-bindings.js";
import { wireCanvasPicking } from "./boot/picking.js";
import { wireHeaderToggles } from "./boot/header-toggles.js";
import { wireSpeedSlider } from "./boot/speed-slider.js";
import { buildStructureMeshes } from "./boot/meshing.js";
import { wireFocus } from "./boot/focus.js";
import { wireLegends } from "./boot/legends.js";
import { wireViews } from "./boot/views.js";
import { launchScene } from "./boot/launch.js";
import { createRenderLoop } from "./boot/render-loop.js";

// UI string lookup (js/i18n.js, a classic script that ran before this module).
// `t(key, vars)` returns the current-language UI string; data strings are
// already resolved to the chosen language by js/data.js.
const { t } = window.__I18N__;

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

  const { meshes, meshById } = await buildStructureMeshes({ data, scene, loading });

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

  // Camera focus (framing a node, recentering): a smooth tween advanced in the render
  // loop; grabbing the controls cancels it so a drag always wins.
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

  // Every focus / select helper (boot/focus.js). `autoSpreadIfDeep` is late-bound:
  // its owner, wireControls, registers URL keys that must follow the Drugs list's.
  const {
    circuitAnim, drugAnim, receptorMarkers,
    focusCircuit, focusDrug, focusEffect, focusEnzyme, focusProjectionGroup, focusTarget,
    selectConnection, selectStructure,
  } = wireFocus({
    arrows, autoSpreadIfDeep: (...a) => autoSpreadIfDeep(...a), data, focus, info,
    isolateGroupFor, meshById, openDetailTab, scene, selection, tabs, urlState,
  });

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

  wireCanvasPicking({
    arrows, camera, canvas: renderer.domElement, focus, isolateGroupFor, labels, meshes,
    selectConnection, selection, selectStructure, tabs,
  });

  const projVis = createProjectionVisibility(arrows, labels);
  wireLegends({
    arrows, circuitAnim, data, focusCircuit, focusProjectionGroup, info, meshById, projVis,
    selectStructure, selection, urlState,
  });

  // The Data browser + Simulation tabs, and the Sources popup's tally. The About modal
  // and setNo3d are wired further down, so both are late-bound.
  const { NODES_TAB_KEY, showNodeBrowser, showSimulation, simulation } = wireViews({
    arrows, data, focusCircuit, focusDrug, focusProjectionGroup, focusTarget, info, meshById,
    openDataFiles: () => aboutModal.openDataFiles(), openDetailTab, selectConnection,
    selectStructure, setNo3d: (...a) => setNo3d(...a), sourcingModal, urlState,
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


  const { intro } = launchScene({
    aboutModal, arrowRetrim, arrows, autoSpread, camera, changelog, controls, data, focus,
    focusDrug, focusProjectionGroup, focusTarget, legendModal, loading, meshById, meshes,
    NODES_TAB_KEY, selection, selectStructure, setNo3d: (...a) => setNo3d(...a),
    showNodeBrowser, sourcingModal, tabs, toolbar,
  });

  wireUrlBindings({
    aboutModal, arrows, changelog, data, focusCircuit, focusDrug,
    focusEffect, focusEnzyme, focusProjectionGroup, focusTarget, legendModal, meshes,
    selectConnection, selectStructure, shortcutsHelp,
    showNodeBrowser, showSimulation,
    simulation, sourcingModal, tabs, urlState,
  });

  // Apply the incoming URL (after the intro exists, so a focused node cancels the
  // assemble intro rather than fighting its explode tween), then keep the address bar
  // mirroring the UI: copying it is just selecting the URL bar, no dedicated button.
  // The sync also normalizes a legacy / hand-written link into the canonical fragment.
  if (urlState.applyHash()) intro.cancel();
  urlState.sync();
  urlState.start();

  const loop = createRenderLoop({ renderer, baseDpr, controls, circuitAnim });
  const invalidate = loop.invalidate;

  const updateSpeedRow = wireSpeedSlider({ invalidate, urlState,
    animating: () => drugAnim.active || receptorMarkers.active || circuitAnim.active });

  // Panel header toggles: day/night + the panel-only "reading" mode.
  const { no3dOn, setNo3d } = wireHeaderToggles({ theme, expandPanel, invalidate, intro, urlState });

  loop.start({
    scene, camera, labels, urlState, intro, autoSpread, arrowRetrim, focus,
    receptorMarkers, drugAnim, arrowWidth, seeThrough, no3dOn, updateSpeedRow,
  });
}

main();
