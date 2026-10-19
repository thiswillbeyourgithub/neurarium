// The guided tour's steps (js/tour.js runs them): each step's before() drives the real
// viewer, so every selector and data-tour-* hook a step names must still exist (walk it
// with tools/tour_walk.py after any UI change).

import { applyExplode } from "../scene/explode.js";
import { createTour } from "../tour.js";

const { t, tHtml } = window.__I18N__;

export function createViewerTour({
  arrows, autoSpread, controls, data, focus, focusDrug, focusProjectionGroup,
  focusTarget, legendModal, meshById, meshes, NODES_TAB_KEY, selection,
  selectStructure, setNo3d, showNodeBrowser, sourcingModal, tabs, toolbar,
}) {
  // ---- Guided tour ("See the tutorial") ----------------------------------------------
  // A coach-mark walkthrough (js/tour.js) that shows the main features live: each
  // step's before() drives the real viewer (spread the brain, focus a circuit /
  // receptor / drug, open a section) rather than showing a static picture. It
  // auto-runs ONCE on a first visit (fired from the intro's onSettle below, so it
  // starts only after the assemble settles) and is replayable from the About popup.
  const tourEl = (id) => document.getElementById(id);
  // Expand the controls panel + show the Settings pane (a focus demo swaps the
  // pane out for the Details view, so a later control-spotlight step needs it back).
  const tourExpandPanel = () => {
    const body = tourEl("controls-body");
    if (body && body.hidden) {
      tourEl("controls-toggle")?.setAttribute("aria-expanded", "true");
      body.hidden = false;
    }
    tabs.showSettings();
  };
  // Open the Settings sub-pane (the sliders + toolbar buttons a control spotlight
  // targets); tourCollapseSettings folds it so the browse sections sit up top.
  const tourEnsurePanel = () => {
    tourExpandPanel();
    const cs = tourEl("controls-settings-body");
    if (cs && cs.hidden) tourEl("controls-settings-toggle")?.click();
  };
  const tourCollapseSettings = () => {
    const cs = tourEl("controls-settings-body");
    if (cs && !cs.hidden) tourEl("controls-settings-toggle")?.click();
  };
  const tourOpenSection = (name) => {
    tourEnsurePanel();
    const body = tourEl(`${name}-body`);
    if (body && body.hidden) tourEl(`${name}-toggle`)?.click();
  };
  // Collapse a section so the "tap to open it" interactive step visibly opens it.
  // Runs from a step's before() (which re-fires on Back), so it sets state, not toggles.
  const tourCloseSection = (name) => {
    tourEnsurePanel();
    const body = tourEl(`${name}-body`);
    if (body && !body.hidden) tourEl(`${name}-toggle`)?.click();
  };
  // The browse sections the tour rings as one group (the "Browse the data" step) and
  // collapses beforehand. In on-screen order, which is also the order the caption
  // names them in, so the ring and the sentence read as one list. Enzymes is in it
  // because it sits BETWEEN the others in the panel: the group ring spans them all
  // whether or not it is named, so leaving it out would ring an unnamed section.
  const TOUR_SECTIONS = ["drugs", "receptors", "enzymes", "effects", "structures", "projections"];
  // Collapsing a list is only half of "put it back": a filter the visitor typed
  // survives the fold, so the next step's "tap Olanzapine" can ring a row that the
  // reopened list no longer contains. Cleared through the input's own event, which
  // is what the live filter and the URL both listen to, so this is a typed clear
  // rather than a value assignment the rest of the app never hears about.
  const tourClearFilters = () => {
    for (const id of ["drugs-filter", "search-input"]) {
      const el = tourEl(id);
      if (el && el.value) {
        el.value = "";
        el.dispatchEvent(new Event("input"));
      }
    }
  };
  const tourCollapseSections = () => {
    tourClearFilters();
    for (const name of TOUR_SECTIONS) {
      const b = tourEl(`${name}-body`);
      if (b && !b.hidden) tourEl(`${name}-toggle`)?.click();
    }
  };
  // Clear any focus / isolate / tab / open sourcing modal a previous step left, so
  // each demo starts from a clean scene (idempotent: steps re-run on Back too).
  const tourReset = () => {
    tabs.closeAll();
    selection.clear();
    sourcingModal.close();
    legendModal.close();
  };
  // A FULL reset for the launch of the tour (and its end): everything tourReset does,
  // plus un-spread the brain, recenter the camera, collapse the browse sections, fold
  // the search box, and re-expand the panel. Wired to step 1's before(), so every entry
  // point (auto-start, ?tour=1, the About replay) runs it via go(0) at launch: a
  // derailed UI (a spread brain, an open list, an active animation, a stray search)
  // can never carry into the tour.
  const tourFullReset = () => {
    tourReset();
    // The tour is a tour of a 3D scene, so it always runs (and ends) with the brain
    // on screen, whatever reading mode a step (or the visitor) left behind. Borrowed,
    // never persisted: the visitor's own stored preference is theirs to keep.
    setNo3d(false, { persist: false });
    const sl = tourEl("explode");
    if (sl) { sl.value = "0"; applyExplode(meshes, 0, arrows); }
    const sb = tourEl("search");
    if (sb && !sb.hidden) tourEl("search-toggle")?.click();
    // Force a deterministic launch view: panel expanded, Settings sub-pane open
    // (the sliders visible), the Settings tab focused (tourEnsurePanel), and the
    // browse sections collapsed. So the tour always opens on the same clean state
    // whatever the user left behind.
    tourEnsurePanel();
    tourCollapseSections();
    focus.recenter();
  };

  // The nodes the guided story walks through (resolved once; a missing id just makes
  // its step a caption). The story: Olanzapine (drug) -> its H1 receptor -> a structure
  // (hippocampus) -> a projection system (dopamine), each tapped hands-on.
  const tourOlanzapine = data.drugs.find((d) => d.id === "olanzapine");
  const tourH1 = data.targets.find((x) => x.id === "h1");
  const tourStructMesh = meshById.get("hippocampus_R"); // meshes[0] (R) is the row's pick
  const tourDopGroup = data.projectionGroupsByKey.get("kind:dopaminergic");
  // Direct focus helpers for the structure / projection-group re-open hooks (their
  // legend rows toggle isolate, so re-clicking is not idempotent; focus directly).
  const tourShowStruct = () => selectStructure(tourStructMesh, { frame: true, isolate: true });
  const tourShowDopGroup = () => focusProjectionGroup(tourDopGroup, { frame: true });
  // Re-open a node's detail panel only if it is not already the active tab, so a
  // detail sub-step's before() (which re-runs on Back) never restarts the focus /
  // animation while the user is reading it.
  const tourEnsureTab = (key, node, show) => () => {
    if (node && tabs.activeKey() !== key) show(node);
  };
  // Reset the open details panel to its top. Paired with a tourGateScroll "read this
  // panel" step (24 structure, 28 projection system): if the pane were left scrolled
  // near the bottom (a Back into the step, or a prior deep scroll), the gate's
  // "reached the bottom" test would fire on the user's very first gesture and autoskip
  // the step before they read a word. Forcing scrollTop = 0 here (synchronously, before
  // the gate arms) makes the panel always start at the illustration.
  const tourPanelToTop = () => {
    const pane = document.getElementById("details-pane");
    if (pane) pane.scrollTop = 0;
  };
  // A "read this panel" step's before(): re-open the node's tab if needed, then always
  // start the panel at its top (see tourPanelToTop) so the scroll gate can't autoskip.
  const tourReadPanel = (key, node, show) => () => {
    tourEnsureTab(key, node, show)();
    tourPanelToTop();
  };
  // The olanzapine panel, re-opened only when it is not already the active tab: the
  // drug walk-through (Acts on -> Metabolism -> Psychotropic interactions -> the H1 row) is
  // four sub-steps reading ONE panel, so they share this before().
  const tourDrugPanel = tourEnsureTab("drug:olanzapine", tourOlanzapine, focusDrug);
  // Every detail panel's sections start folded (see foldSections): a step that points
  // INTO one (its rows, or a row in it) runs `ensure` (opens the panel), then opens
  // that section.
  const tourOpenSec = (ensure, sec) => () => {
    ensure();
    const d = document.querySelector(`#details-pane [data-tour-sec="${sec}"]`);
    if (d) d.open = true;
  };
  const tourDrugSec = (sec) => tourOpenSec(tourDrugPanel, sec);
  // The drug panel's collapsed "Psychotropic interactions" <details> (see showDrug). Its step
  // is hands-on (the user opens it), so the step's before() re-collapses it: a Back
  // into the step must leave something to open.
  const tourPkDetails = () =>
    document.querySelector('#details-pane [data-tour-sec="pk"]');
  const tourCollapsePk = () => { const d = tourPkDetails(); if (d) d.open = false; };

  // --- Gesture gates: return a teardown; call signal() when the action happens. See
  // js/tour.js (a gate keeps Next greyed until fired, or auto-advances on gateAdvances).
  const tourGateRotate = (signal) => {
    // OrbitControls "start" fires on a real pointer-down drag, NOT on idle
    // auto-rotate, so a passive spin never trips the gate.
    const on = () => signal();
    controls.addEventListener("start", on);
    return () => controls.removeEventListener("start", on);
  };
  const tourGateSlider = (signal) => {
    // playSequence sets slider.value in JS (no "input" event), so only a real grab fires.
    const el = tourEl("explode");
    if (!el) return () => {};
    const on = () => signal();
    el.addEventListener("input", on);
    return () => el.removeEventListener("input", on);
  };
  // Ungrey (and, with gateAdvances, move on) once a modal closes (its `hidden`
  // attribute flips), watched via a MutationObserver so no blocker is needed over
  // the popup: it stays scrollable + its own close X directly clickable.
  const tourGateModalClosed = (id) => (signal) => {
    const el = tourEl(id);
    if (!el) return () => {};
    const obs = new MutationObserver(() => { if (el.hidden) signal(); });
    obs.observe(el, { attributes: true, attributeFilter: ["hidden"] });
    return () => obs.disconnect();
  };
  const tourGateScroll = (signal) => {
    // Fire once the user has scrolled the details panel "enough": to near the bottom of
    // its scrollable content (or on any scroll gesture if there is almost nothing to
    // scroll, so a short panel can't trap them). Paired with gateAdvances, that moves the
    // tour on by itself rather than merely ungreying Next. A real gesture (wheel / touch /
    // arrow keys) must happen first, so the step's own programmatic scrollTo (which emits
    // "scroll" but no gesture) never trips it.
    const el = document.getElementById("details-pane");
    if (!el) return () => {};
    const NEAR = 24; // px from the bottom that counts as "scrolled enough"
    let userScrolled = false;
    const check = () => {
      if (!userScrolled) return;
      const room = el.scrollHeight - el.clientHeight;
      if (room <= NEAR || el.scrollTop >= room - NEAR) signal();
    };
    const mark = () => { userScrolled = true; check(); };
    el.addEventListener("wheel", mark, { passive: true });
    el.addEventListener("touchmove", mark, { passive: true });
    el.addEventListener("keydown", mark);
    el.addEventListener("scroll", check, { passive: true });
    return () => {
      el.removeEventListener("wheel", mark);
      el.removeEventListener("touchmove", mark);
      el.removeEventListener("keydown", mark);
      el.removeEventListener("scroll", check);
    };
  };
  // Any open detail panel's illustration AND its description text, as one group
  // highlight (the wiki figure carries data-tour-sec="wiki"; the live/baked lead lands
  // in .info-desc paragraphs beside it). Union-highlighted so a "read about it" step
  // frames both, not just the picture. Generic: works for a structure / receptor /
  // projection-group panel alike.
  const tourPanelIntro = () => {
    const pane = document.getElementById("details-pane");
    if (!pane) return [];
    const els = [];
    const fig = pane.querySelector('[data-tour-sec="wiki"]');
    if (fig) els.push(fig);
    pane.querySelectorAll(".info-desc").forEach((p) => els.push(p));
    return els;
  };
  // The active detail tab's close button (the × on the open panel's chip), for the
  // hands-on "close this panel" step; null when no tab is open.
  const tourActiveTabClose = () =>
    document.querySelector(".detail-tab.active .detail-tab-close");
  // The demos are hands-on: the user opens each list and taps the highlighted row
  // themselves (interactive steps in js/tour.js advance on that real tap). The row
  // hooks are `data-tour-id` attributes set in the legend builders; these sample
  // ids must exist in the data (a stale id just leaves the row untargetable).
  // Round a count DOWN to a friendly floor (179 -> 150, 52 -> 50) so the tour's
  // "150+" teasers are always truthful (an undercount), never overstating.
  const tourCount = (n) => { const step = n >= 100 ? 50 : 10; return Math.floor(n / step) * step; };
  const tourSteps = [
    // 1. Welcome (caption). Fully reset the UI here so any entry point starts clean.
    { title: t("tour.welcome.title"), body: tHtml("tour.welcome.body"),
      dim: true, placement: "center", before: tourFullReset },
    // 2. Rotate: dim just the panel (veil), keep the brain draggable; Next ungreys
    //    once the user actually drags it.
    { title: t("tour.rotate.title"), body: tHtml("tour.rotate.body"),
      dim: false, placement: "brain", veil: ["#controls"], gate: tourGateRotate,
      before: tourReset },
    // 3. Separate: sweep the slider off -> max -> middle (replays on Back->Next); Next
    //    ungreys once the user grabs the slider themselves.
    { title: t("tour.separate.title"), body: tHtml("tour.separate.body"),
      target: "#explode", dim: false, spotlightOnly: true, gate: tourGateSlider,
      clickThrough: "#explode",
      before: () => { tourReset(); tourEnsurePanel(); autoSpread.playSequence([0, 1, 0, 0.5]); } },
    // 4-5. The legend, before any data: the scene is already colour-coded, so the key
    //    to it belongs early. Same open/close shape as the Sources pair below.
    { title: t("tour.legendOpen.title"), body: tHtml("tour.legendOpen.body"),
      target: "#legend-toggle", interactive: true, scrollTo: true,
      before: () => { tourReset(); tourEnsurePanel(); } },
    { title: t("tour.legendLook.title"), body: tHtml("tour.legendLook.body"),
      target: "#legend-close", dim: false, spotlightOnly: true,
      clickThrough: "#legend-modal", bubbleDock: "bottom",
      gate: tourGateModalClosed("legend-modal"), gateAdvances: true,
      before: () => legendModal.open() },
    // 6. Sourcing: tap the Sources button (opens the popup, auto-advances).
    { title: t("tour.sourcesOpen.title"), body: tHtml("tour.sourcesOpen.body"),
      target: "#sourcing-toggle", interactive: true, scrollTo: true,
      before: () => { tourReset(); tourEnsurePanel(); } },
    // 7. Sourcing detail: explain the popup, ringing just its close X with NO page
    //    dim (spotlightOnly) so the breakdown it points at stays fully readable. No
    //    blocker (a gate, not interactive), so the popup stays scrollable; clickThrough
    //    keeps its controls (incl. the X) live, and closing it advances (gateAdvances).
    { title: t("tour.sourcesDetail.title"), body: tHtml("tour.sourcesDetail.body"),
      target: "#sourcing-close", dim: false, spotlightOnly: true,
      clickThrough: "#sourcing-modal", bubbleDock: "bottom",
      gate: tourGateModalClosed("sourcing-modal"), gateAdvances: true,
      before: () => sourcingModal.open() },
    // 8-9. The Data browser, straight after "every fact is graded": that popup gives
    //    the tally, this list gives the facts it counted. Opening it borrows the
    //    reading mode (the rows are a wide table), which sets up the two view
    //    toggles below: the visitor has just seen the brain go away, so the button
    //    that brings it back has something to undo.
    { title: t("tour.nodesOpen.title"), body: tHtml("tour.nodesOpen.body"),
      target: "#nodes-toggle", interactive: true, scrollTo: true,
      before: () => {
        tourReset();
        setNo3d(false, { persist: false });
        tourExpandPanel();
        tourCollapseSettings();
        tourCollapseSections();
      } },
    { title: t("tour.nodesLook.title"), body: tHtml("tour.nodesLook.body"),
      target: () => ["#nodes-filter", ".node-filters"],
      dim: false, scrollTo: true, scrollAlign: "top",
      before: () => {
        if (tabs.activeKey() !== NODES_TAB_KEY) showNodeBrowser();
        setNo3d(true, { persist: false });
      } },
    // 10-11. The two view toggles, as a pair of opposites: bring the 3D back (the
    //    browser above hid it), then fold the panel away and leave the brain alone.
    { title: t("tour.show3d.title"), body: tHtml("tour.show3d.body"),
      target: "#toggle-3d", interactive: true,
      before: () => { tourReset(); setNo3d(true, { persist: false }); tourExpandPanel(); } },
    { title: t("tour.collapsePanel.title"), body: tHtml("tour.collapsePanel.body"),
      // stayAfterTap: the fold is the thing to watch, so the step holds while the
      // panel collapses and Next (not the tap) moves on. The ring hugs the
      // "neurarium" title, not the full-row hit button, whose centre sits on the
      // byline's author link; a tap on the title falls through to that button.
      target: "#controls-header .panel-title", tapTarget: "#controls-toggle",
      interactive: true, stayAfterTap: true,
      before: () => {
        tourReset();
        setNo3d(false, { persist: false });
        tourExpandPanel();
      } },
    // 12. Browse: highlight the five sections as a group, each teased with a rounded-
    //    down count ("150+"), always an honest undercount (see tourCount).
    { title: t("tour.browse.title"),
      body: tHtml("tour.browse.body", {
        structures: tourCount(data.structures.length),
        // data.projections is L/R-expanded at load (symmetric twins share one id),
        // so its length double-counts; the node count (what the collapsed browse
        // list shows) is the canonical tally total.
        projections: tourCount(
          data.meta?.provenanceStats?.by_kind?.projections?.total ??
            data.projections.length,
        ),
        receptors: tourCount(data.targets.length),
        drugs: tourCount(data.drugs.length),
      }),
      target: () => TOUR_SECTIONS.map((n) => `#${n}-toggle`),
      scrollTo: true, // the four headings must land in view as a block, not half off it
      before: () => { tourReset(); tourExpandPanel(); tourCollapseSettings(); tourCollapseSections(); } },
    // 13-14. Drugs first: open the list, then tap Olanzapine (opens its panel and plays
    //    the effect animation live on the brain).
    { title: t("tour.openDrugs.title"), body: tHtml("tour.openDrugs.body"),
      target: "#drugs-toggle", interactive: true, scrollTo: true,
      before: () => { tourReset(); tourCloseSection("drugs"); } },
    { title: t("tour.drugTap.title"), body: tHtml("tour.drugTap.body"),
      target: '[data-tour-id="drug:olanzapine"]', interactive: true, scrollTo: true,
      before: () => tourOpenSection("drugs") },
    // 15. The drug's "Direct molecular targets" list (dim:false so the live animation stays visible). The
    //    body flags the drug animations as the least-scientific, still-WIP part.
    { title: t("tour.drugActs.title"), body: tHtml("tour.drugActs.body"),
      target: '[data-tour-sec="bindings"]', dim: false, scrollTo: true, scrollAlign: "top",
      before: tourDrugSec("bindings") },
    // 16-17. Still the same panel, further down: the pharmacokinetic half. The enzymes
    //    that clear it (sourced nodes), then the drug -> drug interactions those roles
    //    imply, collapsed so the user opens it themselves (stayAfterTap keeps the step
    //    up so the list it reveals is readable).
    { title: t("tour.drugMetabolism.title"), body: tHtml("tour.drugMetabolism.body"),
      target: '[data-tour-sec="metabolism"]', dim: false, scrollTo: true,
      scrollAlign: "top", before: tourDrugSec("metabolism") },
    { title: t("tour.drugPk.title"), body: tHtml("tour.drugPk.body"),
      target: () => {
        const d = tourPkDetails();
        return d ? d.querySelector("summary") : null;
      },
      interactive: true, stayAfterTap: true, dim: false, scrollTo: true,
      scrollAlign: "top", // the list it opens unfolds BELOW the summary: leave it room
      before: () => { tourDrugPanel(); tourCollapsePk(); } },
    // 18. Follow one binding, the H1 receptor row, to that receptor's own panel.
    { title: t("tour.drugToReceptor.title"), body: tHtml("tour.drugToReceptor.body"),
      target: '[data-tour-id="ixtarget:h1"]', interactive: true, scrollTo: true,
      before: tourDrugSec("bindings") },
    // 19-20. Walk the receptor (H1) panel: how it is classified, then where it is found.
    { title: t("tour.receptorFacts.title"), body: tHtml("tour.receptorFacts.body"),
      target: '[data-tour-sec="facts"]', dim: false, scrollTo: true,
      before: tourEnsureTab("target:h1", tourH1, focusTarget) },
    { title: t("tour.receptorRegions.title"), body: tHtml("tour.receptorRegions.body"),
      target: '[data-tour-sec="regions"]', dim: false, scrollTo: true,
      before: tourOpenSec(tourEnsureTab("target:h1", tourH1, focusTarget), "regions") },
    // 21. Back out of the receptor panel by hand (tap its close ×).
    { title: t("tour.closePanel.title"), body: tHtml("tour.closePanel.body"),
      target: tourActiveTabClose, interactive: true,
      before: tourEnsureTab("target:h1", tourH1, focusTarget) },
    // 22-23. Structures: open the list, then tap the hippocampus row (isolates it).
    { title: t("tour.openStructures.title"), body: tHtml("tour.openStructures.body"),
      target: "#structures-toggle", interactive: true, scrollTo: true,
      before: () => tourCloseSection("structures") },
    { title: t("tour.structureTap.title"), body: tHtml("tour.structureTap.body"),
      target: '[data-tour-id="structure:hippocampus"]', interactive: true, scrollTo: true,
      before: () => tourOpenSection("structures") },
    // 24. Read the structure panel (illustration + description; scroll to proceed).
    { title: t("tour.structureLook.title"), body: tHtml("tour.structureLook.body"),
      target: tourPanelIntro, dim: false, scrollTo: true, scrollFree: true,
      gate: tourGateScroll, gateAdvances: true,
      before: tourReadPanel("structure:hippocampus_R", tourStructMesh, tourShowStruct) },
    // 25. Back out of the structure panel by hand.
    { title: t("tour.closePanel.title"), body: tHtml("tour.closePanel.body"),
      target: tourActiveTabClose, interactive: true,
      before: tourEnsureTab("structure:hippocampus_R", tourStructMesh, tourShowStruct) },
    // 26-27. Projections: open the list, then tap a projection SYSTEM (Dopamine), NOT a
    //    circuit; it pins that system's pathways and streams the by-mechanism flow.
    { title: t("tour.openProjections.title"), body: tHtml("tour.openProjections.body"),
      target: "#projections-toggle", interactive: true, scrollTo: true,
      before: () => tourCloseSection("projections") },
    { title: t("tour.projectionTap.title"), body: tHtml("tour.projectionTap.body"),
      target: '[data-tour-id="group:kind:dopaminergic"]', interactive: true, scrollTo: true,
      before: () => tourOpenSection("projections") },
    // 28. Read the projection-system panel (member pathways + description).
    { title: t("tour.projectionLook.title"), body: tHtml("tour.projectionLook.body"),
      target: tourPanelIntro, dim: false, scrollTo: true, scrollFree: true,
      gate: tourGateScroll, gateAdvances: true,
      before: tourReadPanel("group:kind_dopaminergic", tourDopGroup, tourShowDopGroup) },
    // 29-30. Get to search by hand: tap Settings (back to the main panel), then the
    //    magnifier (opens the search box). Both auto-advance on the real tap.
    { title: t("tour.backToSettings.title"), body: tHtml("tour.backToSettings.body"),
      target: "#tab-settings", interactive: true,
      before: tourEnsureTab("group:kind_dopaminergic", tourDopGroup, tourShowDopGroup) },
    { title: t("tour.openSearch.title"), body: tHtml("tour.openSearch.body"),
      target: "#search-toggle", interactive: true,
      before: () => tabs.showSettings() },
    // 31. Search demo: the box is open + live (dim:false); clickThrough keeps it
    //    clickable under the guard so they can focus + type a name.
    { title: t("tour.search.title"), body: tHtml("tour.search.body"),
      target: "#search .search-modal", dim: false, clickThrough: "#search",
      before: () => { tourExpandPanel(); toolbar.openSearchWithQuery(""); } },
    // 32. Wrap (spotlight the About button, where the tour can be replayed).
    { title: t("tour.wrap.title"), body: tHtml("tour.wrap.body"),
      target: "#about-toggle", before: () => { tourReset(); tourEnsurePanel(); } },
  ];
  const tour = createTour({
    steps: tourSteps,
    labels: {
      next: t("tour.next"), back: t("tour.back"), done: t("tour.done"),
      skip: t("tour.skip"), aria: t("tour.aria"), scrollHint: t("tour.scrollHint"),
      step: (n, total) => t("tour.step", { n, total }),
    },
    seenKey: "neurarium:tourSeen",
    // Restore a clean default view once the tour ends (completed or skipped).
    onEnd: tourFullReset,
  });

  return {
    tour, tourEl,
  };
}
