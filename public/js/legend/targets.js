// The "Receptors & targets" browse section, grouped by neurotransmitter system.

import { addLegendItem, reflectRows } from "./item.js";

const { t } = window.__I18N__;

/**
 * Group targets under their neurotransmitter `system`, the one ordering the whole app
 * lists receptors in: heaviest system first, the system-less "_other" bucket pinned
 * last however heavy, members lexicographic within a system (`numeric` so 5-HT2
 * precedes 5-HT10, `base` sensitivity folding case + accents). What "heaviest" means
 * is the caller's: the legend weighs a target by its knowledge nodes, the structure
 * panel by one each (so a region's biggest system leads).
 * @param {object[]} targets
 * @param {(target: object) => number} weightOf
 * @returns {Array<[string, object[]]>} `[systemKey, members]`, in display order
 */
export function groupTargetsBySystem(targets, weightOf) {
  const bySystem = new Map();
  for (const tgt of targets || []) {
    const key = tgt.system || "_other";
    if (!bySystem.has(key)) bySystem.set(key, []);
    bySystem.get(key).push(tgt);
  }
  for (const [, list] of bySystem) {
    list.sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }));
  }
  const weight = new Map([...bySystem].map(
    ([key, list]) => [key, list.reduce((sum, tgt) => sum + weightOf(tgt), 0)]));
  const order = [...bySystem.keys()].filter((k) => k !== "_other");
  order.sort((a, b) => weight.get(b) - weight.get(a));
  if (bySystem.has("_other")) order.push("_other");
  return order.map((key) => [key, bySystem.get(key)]);
}

/**
 * Build the merged "Receptors & targets" legend section from the live dataset
 * (#receptors-body): the unified `data.targets` list (every modeled receptor plus
 * every non-receptor drug target: transporters, enzymes, channels, receptor
 * groups), grouped by neurotransmitter `system`, so a transporter like SERT sits
 * under "Serotonergic" beside the 5-HT receptors. System headings are ordered by
 * **total knowledge nodes** (biggest first: the sum over the system's targets of
 * each target's own node + its "Regional distribution" regions + the drug bindings on it, so a
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
export function buildTargetLegend(data, onPick) {
  const container = document.getElementById("receptors-body");
  if (!container) return () => {};
  container.replaceChildren();
  const rows = []; // { row, id } for the focusable entries

  const families = data.meta.receptorFamilyLabels || {};
  const drugsByTarget = data.drugsByTarget || new Map();

  // Each target's "size" is its knowledge nodes: the target itself, its expression
  // "Regional distribution" regions (a ubiquitous receptor is one "throughout the brain" node),
  // and the drug bindings acting on it (data.drugsByTarget, deduped one per drug).
  // A system's weight is the sum over its targets, so a heavily-expressed,
  // heavily-drugged system (dopaminergic) outweighs a sparse one (melatoninergic).
  const nodeCount = (tgt) => {
    const locs = tgt.receptor
      ? (tgt.receptor.ubiquitous ? 1 : tgt.receptor.locations.length)
      : (tgt.locationBases || []).length;
    const drugs = (drugsByTarget.get(tgt.id) || []).length;
    return 1 + locs + drugs;
  };
  for (const [key, list] of groupTargetsBySystem(data.targets, nodeCount)) {
    if (!list.length) continue;
    const h = document.createElement("h2");
    h.textContent = key === "_other" ? t("targets.otherSystem") : (families[key] || key);
    h.dataset.tourSystem = key; // guided-tour hook: spotlight a whole system's box
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
        row.dataset.tourId = `target:${tgt.id}`; // guided-tour target hook
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

  return reflectRows(rows);
}
