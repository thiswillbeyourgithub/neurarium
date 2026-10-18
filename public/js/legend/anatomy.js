// The anatomy legend: Structures, Projections and Circuits sections, plus the
// projection visibility filter they drive.

import { addLegendItem } from "./item.js";
import { stripSide } from "../util.js";

const { t } = window.__I18N__;

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
 * Shared control of which projection arrows are visible, so the global "Show
 * projections" checkbox, the legend's off-by-default "Hypothetical pathways"
 * toggle and the current focus compose into one final per-arrow visibility instead
 * of fighting over setVisible(). An arrow shows when it is either established or
 * (when tentative) its section has been toggled on, AND projections aren't globally
 * hidden OR the arrow is one the current focus lights.
 *
 * That last exemption is what lets "Show projections" default to off: the ambient
 * ~100-arrow tangle stays out of the way, but focusing a circuit / a drug's systems
 * / a structure still draws exactly its own pathways, which the selection controller
 * only ever dimmed (it owns opacity, never visibility).
 * @param {import("./arrows.js").ProjectionArrow[]} arrows
 * @param {{refresh: () => void}} labels  Refreshed after a change so the
 *   connection labels follow their arrows' visibility.
 */
export function createProjectionVisibility(arrows, labels) {
  let allHidden = false;
  let tentativeShown = false;
  let focusArrows = null; // the current focus's arrows, exempt from allHidden
  const apply = () => {
    for (const a of arrows) {
      const global = !allHidden || (focusArrows !== null && focusArrows.has(a));
      a.setVisible(global && (!a.tentative || tentativeShown));
    }
    labels.refresh();
  };
  // Same members = same result, and this is fed from selection.apply(), which also
  // runs on every hover; without the compare each hover would re-walk the arrows and
  // rebuild the connection labels.
  const same = (a, b) => {
    if (a === b) return true;
    if (a === null || b === null || a.size !== b.size) return false;
    for (const x of a) if (!b.has(x)) return false;
    return true;
  };
  return {
    apply,
    get allHidden() { return allHidden; },
    setAllHidden(v) { allHidden = v; apply(); },
    get tentativeShown() { return tentativeShown; },
    setTentativeShown(v) { tentativeShown = v; apply(); },
    /** The arrows the live focus lights (empty/null = no focus). */
    setFocusArrows(set) {
      const next = set && set.size > 0 ? set : null;
      if (same(next, focusArrows)) return;
      focusArrows = next;
      if (allHidden) apply(); // shown-anyway: the exemption changes nothing
    },
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
export function projectionGroups(established, meta, signMode) {
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
 * @param {(host: HTMLElement, ownerKind: string, ownerId: string, slot: string) => number}
 *   appendAddons  the info panel's addon hook (see createInfoPanel), passed in because
 *   the Projections section carries an addon slot of its own and an addon must render
 *   identically here and in a detail panel.
 * @returns {(isolated: Set<THREE.Mesh>|null, focusedArrows: Set<object>) => void}
 */
export function buildLegend(data, meshById, arrows, selection, projVis, circuitAnim, signColorMode, onPickStructure, onFocusCircuit, onFocusProjectionGroup, appendAddons) {
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
  // The Projections section's own addon slot, drawn above its first heading: the
  // caveat it carries (bilaterality) is true of every pathway below at once, so it is
  // anchored on the SECTION rather than on a node, and it reads before the rows it
  // qualifies rather than after them. Rebuilt with the rest on a colour-mode toggle.
  appendAddons(projectionsBody, "section", "projections", "section.projections");

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
        // base = the hemisphere-stripped structure id, a stable guided-tour hook.
        entry = { color: s.color, meshes: [], base: stripSide(s.id) };
        byLabel.set(label, entry);
      }
      const mesh = meshById.get(s.id);
      if (mesh) entry.meshes.push(mesh);
    }
    const groupMeshes = [];
    for (const [label, entry] of byLabel) {
      const row = addLegendItem(structuresBody, entry.color, label);
      if (entry.base) row.dataset.tourId = `structure:${entry.base}`; // guided-tour hook
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
      if (g.dataKey) row.dataset.tourId = `group:${g.dataKey}`; // guided-tour hook
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
      row.dataset.tourId = `circuit:${circuit.id}`; // guided-tour target hook
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
