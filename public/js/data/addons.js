// Addon nodes: each resolved onto its owner and indexed by its insertion slot.

import { groupBy } from "../util.js";
import { localize } from "./localize.js";
import { strongestGrade } from "./sources.js";

export function resolveAddons({ drugs, targets, byId, v }, addonRecords) {
  const { addonSections, addonTones } = v;
  // Addon nodes: a sourced annotation carrying its OWN insertion point (see
  // tools/data_generators/addons.py). Nothing downstream knows what a given addon
  // says: the record names the node it anchors to (`owner_kind` + `owner`) and the
  // panel `slot` it belongs in, so a panel asks "anything for this slot?" and the
  // data answers. Keyed by exactly that question, so the lookup is one Map.get.
  // The anchored node, resolved ONCE here rather than in each consumer: an addon is
  // listed in the Data browser and exemplified in the Sources popup, and both need
  // the owner's display name and a way to open its panel. `focus` is the navigation
  // recipe ({nav, arg}) those views hand to their own nav table, so neither has to
  // know that a structure navigates by id while a drug navigates by object.
  const addonOwner = (kind, id) => {
    // A section addon has no node to open: it annotates the browse view its claim is
    // about (the caveat is already sitting where it applies), so it resolves to the
    // section's label and a null focus, which every consumer already handles (an
    // unfocusable drug resolves the same way).
    if (kind === "section") {
      return { name: localize(addonSections[id]) || id, focus: null };
    }
    if (kind === "drug") {
      const d = drugs.find((x) => x.id === id);
      return d && { name: d.displayName || d.name,
                    focus: d.focusable ? { nav: "drug", arg: d } : null };
    }
    if (kind === "receptor" || kind === "target") {
      const tg = targets.find((x) => x.id === id);
      return tg && { name: tg.name,
                     focus: tg.focusable ? { nav: "target", arg: tg } : null };
    }
    // A structure addon anchors the hemisphere-less base; the scene is keyed by the
    // per-side ids, so focus the right-hand member (a midline region IS its base).
    const sid = byId.has(`${id}_R`) ? `${id}_R` : id;
    const st = byId.get(sid);
    return st && { name: st.base_name || st.name,
                   focus: { nav: "structure", arg: sid } };
  };
  const addons = (addonRecords || []).map((a) => {
    const owner = addonOwner(a.owner_kind, a.owner) || {};
    return {
      ...a,
      ownerKind: a.owner_kind,
      ownerName: owner.name || a.owner,
      focus: owner.focus || null,
      title: a.title ? localize(a.title) : "",
      text: localize(a.text),
      // Reduced to one display grade the same way every other node is, so an addon's
      // pill reads identically in its panel, in the Data browser and in the tally.
      // A `dataset` addon (meta.addon_bases) states something about this dataset,
      // not about the brain or a drug: unsourceable by design, untallied, and drawn
      // with its own neutral pill instead of the red NOSOURCE one.
      provenance: a.basis === "dataset" ? "dataset" : strongestGrade(a.sources),
      glyph: addonTones[a.tone] || "",
    };
  });
  const addonsBySlot = groupBy(addons, (a) => `${a.ownerKind}:${a.owner}:${a.slot}`);
  return { addons, addonsBySlot };
}
