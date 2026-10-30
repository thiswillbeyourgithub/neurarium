// The detail panel: createInfoPanel builds the shared panel kit (pills, sections,
// reference links, addon slots) and returns the show*() views, each in panel/views/.

import { closeOpenTip } from "./tooltip.js";
import { el, btn, flashRow, foldSections, keepSelectionOnSummaries, withSubtitle } from "./dom.js";
import { showEffect } from "./views/effect.js";
import { showCircuit } from "./views/circuit.js";
import { showProjectionGroup } from "./views/projection-group.js";
import { show } from "./views/connection.js";
import { showStructure } from "./views/structure.js";
import { showReceptor } from "./views/receptor.js";
import { showTarget } from "./views/target.js";
import { showEnzyme } from "./views/enzyme.js";
import { showDrug } from "./views/drug.js";
import { makePills } from "./pills.js";
import { makeAddons } from "./addons.js";
import { makeBindings } from "./bindings.js";
import { makeReference } from "./reference.js";
import { makeMetabolism } from "./metabolism.js";
import { makeOtherForms } from "./other-forms.js";
import { makePathways } from "./pathways.js";
import { makeSections } from "./sections.js";
import { makeExpression } from "./expression.js";

const { ofNoun, t } = window.__I18N__;

/**
 * Build the detail panel renderer. The panel is a **node view**: each show*()
 * method renders one node (a connection / structure / receptor / target / drug /
 * circuit / projection group) plus the nodes linked to it (a receptor's "Locations"
 * regions + interacting drugs, a drug's target bindings, a structure's pathways,
 * ...), each linked node clickable to navigate to it. See the Nodes section of
 * CLAUDE.md. It is pure rendering: opening the matching tab + applying the 3D focus
 * is the caller's job (the select* layer in main(), which calls openDetailTab), so
 * this is reused unchanged whether a node is first picked or re-shown via its tab.
 * @param {import("../data.js").BrainData} data
 */
export function createInfoPanel(data, sourcingModal) {
  const body = document.getElementById("info-body");
  // The pane, not #info-body, is the scrolling box (see the overflow rules in
  // index.html); every show*() rebuilds the body inside it.
  const pane = document.getElementById("details-pane");
  if (pane) keepSelectionOnSummaries(pane);
  // Start every view at the top. Replacing the body's children leaves the pane's
  // scrollTop wherever the *previous* (possibly much taller) panel was, so a click
  // deep in a long panel would open the next one already scrolled into its middle,
  // with no visible reason. One helper instead of a line per show*(), so a new view
  // cannot forget it.
  const clearBody = (view = "") => {
    // A pinned tooltip lives in <body>, not in the panel, so it would outlive the
    // row it explains (its reposition only notices on the next scroll).
    closeOpenTip();
    body.innerHTML = "";
    body.dataset.view = view;
    if (pane) pane.scrollTop = 0;
  };
  // Every headed section folded (panel/dom.js foldSections): a freshly opened panel
  // starts collapsed, and a tab the reader comes BACK to gets the sections they had
  // open in it re-opened by panel/tabs.js, per tab.
  const foldBody = () => foldSections(body);
  const nameOf = (id) => data.byId.get(id)?.name || id;
  // Hemisphere-stripped name ("Frontal lobe", not "Right frontal lobe"): used by
  // every pathway list so left/right twins collapse to one row (see pathwayList).
  const baseNameOf = (id) => data.byId.get(id)?.base_name || nameOf(id);

  // The pick handlers below are set by the caller (on*() at the bottom). Each is a
  // stable function forwarding to whatever handler is registered at call time, so a
  // view can capture it before the caller has wired anything.
  const pickHandlers = {};
  const delegate = (key) => (...args) => pickHandlers[key]?.(...args);
  // Set by the caller (onConnection): what to do when a connection row in a
  // structure panel is clicked. The panel only knows projections, so the caller
  // maps the projection to its arrow and does the framing/halo/connection-panel.
  const onConnectionPick = delegate("onConnectionPick");
  // Set by the caller (onTarget): what to do when a binding row in a drug panel is
  // clicked. The panel hands back the resolved target entry; the caller focuses it
  // exactly like its "Receptors & targets" legend row.
  const onTargetPick = delegate("onTargetPick");
  // Set by the caller (onStructure): what to do when a region row in a receptor /
  // target panel's "Locations" list is clicked. The panel hands back the structure
  // *base* id; the caller resolves it to a mesh and jumps to that structure.
  const onStructurePick = delegate("onStructurePick");
  // Set by the caller (onDrug): what to do when a drug row in a receptor / target
  // panel's "Ligands (drugs)" list is clicked. The panel hands back the drug
  // record; the caller focuses it exactly like its Drugs legend row / search pick.
  const onDrugPick = delegate("onDrugPick");
  const onEnzymePick = delegate("onEnzymePick");
  // Set by the caller (onEffect): open an effect's panel (the Effects section, BETA),
  // from a receptor panel's Effects row or a drug panel's derived "could cause" row.
  const onEffectPick = delegate("onEffectPick");
  // Set by the caller (onProjectionGroup): what to do when a projection-group row in
  // a drug panel's "Pharmacodynamics: net neurotransmission" list is clicked. The panel hands back the
  // group record; the caller focuses it exactly like its Projections legend row.
  const onProjectionGroupPick = delegate("onProjectionGroupPick");
  // Set by the caller (onSearch): run a search query. A drug panel's clickable
  // Class / Nomenclature values hand back a `field:"value"` query string; the caller
  // opens the search box pre-filled with it (see wireToolbar.openSearchWithQuery).
  const onSearchPick = delegate("onSearchPick");
  // Set by the caller (onImage): pop a panel illustration up large. The panel hands
  // back (src, alt, {invert}); the caller shows it in the image lightbox.
  const onImagePick = delegate("onImagePick");
  // Resolve a drug binding's `target` key to its merged-list entry, so a binding
  // row can focus that target (a receptor entry shares its id; a non-receptor one
  // its drug_targets key). Only focusable entries become clickable.
  const targetById = new Map(data.targets.map((tg) => [tg.id, tg]));
  const drugById = new Map((data.drugs || []).map((d) => [d.id, d]));
  const enzymeById = new Map((data.enzymes || []).map((e) => [e.id, e]));
  const effectById = new Map((data.effects || []).map((e) => [e.id, e]));

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
  // or null if it doesn't resolve. Lets the "Locations" list group its regions the
  // same way the Structures legend does.
  const groupOfBase = (base) => resolveBase(base)?.group ?? null;

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
        const link = btn("fact-link", lk.text);
        link.addEventListener("click", () => onSearchPick(lk.query));
        wrap.appendChild(link);
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

  // A node's identity line: its "what is this" group heading carrying the node's own
  // source grade pill. Shared by the structure / circuit / group panels, which each
  // state one identity claim (a receptor/target/drug instead pills each fact row). The
  // grade rides this line, never a "Sources" block below the member lists (which would
  // read as grading the members). `always` shows a NOSOURCE pill even when ungraded,
  // for nodes whose badge is required (circuit / group are llm-only today); a structure
  // omits the pill when its anatomy grade is absent. `sub` is an optional
  // plain-language subtitle (dom.js withSubtitle) on its own line below.
  const appendSourcedHeading = (labelText, provenance, sources, always = false, sub = null) => {
    const groupEl = el("div", "info-group", labelText);
    if (always || provenance) {
      groupEl.appendChild(document.createTextNode(" "));
      groupEl.appendChild(nodePill({ provenance, sources }));
    }
    body.appendChild(withSubtitle(groupEl, sub));
  };

  // The panel kit: what the views in panel/views/ take from this closure (each
  // view is `showX(P, ...)`). The literal holds the closure's own state and pick
  // delegates; each panel/*.js helper factory then reads its deps off P and adds its
  // helpers to it, so a factory may only use what the literal or an EARLIER factory
  // provides (keep the call order below dependency-first).
  const P = {
    addFactRow, appendSourcedHeading, baseNameOf, baseResolves, body, clearBody, data,
    drugById, effectById, el, enzymeById, foldBody, groupOfBase, nameOf,
    onConnectionPick, onDrugPick, onEffectPick, onEnzymePick, onImagePick,
    onProjectionGroupPick, onStructurePick, onTargetPick, resolveBase, sourcingModal,
    targetById,
  };
  Object.assign(P, makePills(P));
  Object.assign(P, makeAddons(P));
  Object.assign(P, makeBindings(P));
  Object.assign(P, makeOtherForms(P));
  Object.assign(P, makeReference(P));
  Object.assign(P, makeMetabolism(P));
  Object.assign(P, makePathways(P));
  Object.assign(P, makeSections(P));
  Object.assign(P, makeExpression(P));
  // Factory-made helpers this closure still calls.
  const {
    appendAddons, appendLookupLink, bindingActionPill, kiCorpusRefNode, locationPill,
    makeProvenancePill, nodePill, pathwayList, sourceBackedPill, speciesLabel, withTip,
  } = P;
  return {
    show: (...args) => show(P, ...args),

    showStructure: (...args) => showStructure(P, ...args),

    showReceptor: (...args) => showReceptor(P, ...args),

    showTarget: (...args) => showTarget(P, ...args),

    showEnzyme: (...args) => showEnzyme(P, ...args),

    showEffect: (...args) => showEffect(P, ...args),

    /**
     * Populate the panel for a *drug* (clicking a drug legend/list row or a drug
     * search result): its name, primary category, a Wikipedia link, a one-line
     * description, its class(es) + nomenclature, then the "Pharmacodynamics: binding profile" list of
     * molecular targets (each binding's effect swatch + target name + action,
     * with a note / "speculative" marker when present, and a source pill: its own
     * quote-level source or the drug-level Stahl citation as a fallback).
     */
    // Both opts are "why did this panel open" hints: the clicked row's counterpart is
    // scrolled to + briefly flashed here, so a jump lands on its reason rather than at
    // the top of an unfamiliar panel (see flashRow).
    // opts.highlightMetabolite: a metabolite name, in the "Active metabolites" section.
    //   Used when arriving from a receptor's Interacting-drugs row for a non-modeled
    //   metabolite (which deep-links to its parent, having no standalone view).
    // opts.highlightEnzymes: enzyme ids, in the "Metabolism" section. Used when arriving
    //   from another drug's Interactions row, which names the isoform they share.
    // opts.highlightSection: a section selector (dom.js sectionSelector). Used when
    //   arriving from another stereo form's empty section (panel/other-forms.js).
    showDrug: (...args) => showDrug(P, ...args),

    showCircuit: (...args) => showCircuit(P, ...args),

    showProjectionGroup: (...args) => showProjectionGroup(P, ...args),

    /** Register the handler run when a structure-panel connection row is clicked. */
    onConnection(fn) {
      pickHandlers.onConnectionPick = fn;
    },

    /** Register the handler run when a drug-panel binding (target) row is clicked. */
    onTarget(fn) {
      pickHandlers.onTargetPick = fn;
    },

    /**
     * Register the handler run when a region row in a receptor / target panel's
     * "Locations" list is clicked. Called with the structure base id; the caller
     * resolves it to a mesh and jumps to that structure.
     */
    onStructure(fn) {
      pickHandlers.onStructurePick = fn;
    },

    /**
     * Register the handler run when a drug row in a receptor / target panel's
     * "Ligands (drugs)" list is clicked. Called with the drug record; the caller
     * focuses it exactly like its Drugs legend row / search pick.
     */
    onDrug(fn) {
      pickHandlers.onDrugPick = fn;
    },

    /**
     * Register the handler run when an enzyme row (a drug panel's Metabolism list)
     * is clicked. Called with the enzyme record from `data.enzymes`; the caller
     * opens it exactly like its Enzymes legend row.
     */
    onEnzyme(fn) {
      pickHandlers.onEnzymePick = fn;
    },

    /** Register the handler run when an effect row is clicked (see onEffectPick). */
    onEffect(fn) {
      pickHandlers.onEffectPick = fn;
    },

    /**
     * Register the handler run when a projection-group row in a drug panel's
     * "Pharmacodynamics: net neurotransmission" list is clicked. Called with the group record; the
     * caller focuses it exactly like its Projections legend row / search pick.
     */
    onProjectionGroup(fn) {
      pickHandlers.onProjectionGroupPick = fn;
    },

    /**
     * Register the handler run when a clickable Class / Nomenclature value in a drug
     * panel is clicked. Called with a `field:"value"` search query string; the caller
     * opens the search box pre-filled with it.
     */
    onSearch(fn) {
      pickHandlers.onSearchPick = fn;
    },
    /** Set the handler that enlarges a clicked panel image (the lightbox). */
    onImage(fn) {
      pickHandlers.onImagePick = fn;
    },

    /**
     * The grade pill builder, so a view outside the info panel (the Data browser's
     * rows) badges a node with the very same element the panel does: same tooltip,
     * same verbatim quote / Ki / reasons-to-doubt, same "Click for details" cue.
     * @param {string|null} level a stored grade, or the "uncertain" display grade
     * @param {{sources?: object[], ki?: object, uncertainty?: object[]}} [node] what
     *   backs the claim; omit it for a bare grade badge with no source to show
     */
    provenancePill(level, node) {
      return sourceBackedPill(level === "nosource" ? null : level, node);
    },

    /**
     * Render the Data browser's (detached, state-keeping) container in the Details
     * pane. It is not a show*() view: the browser owns its own DOM so its filter,
     * selects and scroll survive a tab switch, and the panel only hosts it.
     * @param {HTMLElement} elm the container built by js/node-browser.js
     */
    showNodeBrowser(elm) {
      clearBody("browser");
      body.appendChild(el("h2", "info-title", t("panel.nodes")));
      body.appendChild(elm);
    },

    /**
     * Render the Simulation tab's (detached, state-keeping) container in the Details
     * pane, exactly as showNodeBrowser does: the tab owns its own DOM so the picked
     * drugs, the scrub position and the solver's wish list survive a tab switch.
     * @param {HTMLElement} elm the container built by js/simulation.js
     */
    showSimulation(elm) {
      clearBody("simulation");
      body.appendChild(el("h2", "info-title", t("panel.simulation")));
      body.appendChild(elm);
    },

    /**
     * Fill an addon slot that lives OUTSIDE the info panel. The Projections browse
     * section owns one (the bilaterality caveat, anchored on the section rather than
     * on a node), and that section is built by buildLegend, not by a show*() view, so
     * the hook is exported instead of duplicated: an addon must render the same way,
     * with the same source pill, wherever its slot happens to sit.
     */
    appendAddons,
  };
}
