// The drug panel's "Active metabolites" subsection, the top of its Metabolism
// section (see views/drug.js).

import { bindingKi, formatHalfLife } from "./format.js";
import { subSection } from "./dom.js";
import { valueChip } from "../tdm.js";

const { t } = window.__I18N__;

/**
 * Build the Active metabolites subsection, or nothing for a drug with none.
 * @param {object} P  the panel context showDrug receives
 * @param {object} drug  the resolved drug
 * @param {{highlightMetabolite?: string}} opts  showDrug's "why did this open" hints
 * @returns {{sec: ?HTMLElement, flash: ?HTMLElement}} the subsection and the row to
 *   flash (arrived from a metabolite's receptor row), for the caller to mount + flash
 */
export function activeMetabolitesSubsection(P, drug, opts = {}) {
  const {
    bindingRow, drugById, drugNameLink, el, enzymeById, nodePill, onEnzymePick,
    onTargetPick, targetById,
  } = P;
  // Active metabolites: one row per metabolite (its own sourced identity node).
  // A metabolite that is itself a modeled drug links to it (jump via onDrugPick);
  // each shows its own T½ underneath, a bit like a binding's Ki. A non-modeled
  // metabolite's OWN receptor bindings (Wikipedia/PDSP-sourced) are listed under it
  // via the same bindingRow the drug's "Direct molecular targets" uses, so a reader can see what the
  // metabolite hits without hunting each receptor panel. (A linked metabolite shows
  // none here: its bindings live on its own drug row, reachable via the link.)
  if (!drug.metabolites || !drug.metabolites.length) return { sec: null, flash: null };
  const metaEl = subSection(t("drug.metabolites"), "info-metabolites");
  metaEl.dataset.tourSec = "metabolites";
  const ul = el("ul");
  let flashLi = null; // the row to scroll to + flash (opts.highlightMetabolite)
  for (const m of drug.metabolites) {
    const li = el("li", "metab-row");
    if (opts.highlightMetabolite && m.name === opts.highlightMetabolite) flashLi = li;
    const head = el("div", "metab-head");
    const linked = m.drugId ? drugById.get(m.drugId) : null;
    if (linked && m.linkFocusable) {
      // A metabolite that IS a modeled drug: its name is the link to that drug's
      // panel, where its bindings live (never re-listed here: one source of truth).
      const a = drugNameLink(linked, m.name);
      if (linked.bindings.length)
        a.title = t("drug.metabSeeBindings", { n: linked.bindings.length });
      head.appendChild(a);
    } else {
      head.appendChild(el("span", "bind-target", m.name));
    }
    // The shared node pill, so a link another corpus denies reads orange.
    head.appendChild(nodePill(m));
    li.appendChild(head);
    // Which enzyme makes it, each its own sourced node and clickable to that
    // enzyme's panel: the prodrug story (why a CYP2D6 poor metabolizer gets a
    // different drug than the label says). Absent for the metabolites no corpus
    // pins down, which is most of them, so no NOSOURCE row is shown here.
    for (const f of m.formedBy || []) {
      const row = el("div", "metab-formed");
      const text = el("span", "bind-text");
      text.appendChild(el("span", "bind-action", `${t("drug.formedBy")} `));
      const name = el("span", "bind-target", f.label);
      text.appendChild(name);
      if (f.reactionLabel)
        text.appendChild(el("span", "bind-action", ` · ${f.reactionLabel}`));
      row.appendChild(text);
      row.appendChild(nodePill(f));
      const enz = enzymeById.get(f.enzyme);
      if (enz) {
        row.classList.add("clickable");
        row.addEventListener("click", () => onEnzymePick(enz));
      }
      li.appendChild(row);
    }
    const hlStr = formatHalfLife(m.halfLife);
    if (hlStr) {
      li.appendChild(valueChip({ el, nodePill }, {
        label: t("drug.halfLife"), value: hlStr, cls: "metab-hl", bare: true,
        provenance: m.halfLifeProvenance, sources: m.halfLifeSources }));
    }
    // A non-modeled metabolite's OWN sourced receptor bindings (m.ownBindings,
    // resolved in js/data.js from its Wikipedia/PDSP pharmacology). Rendered with
    // the same bindingRow the drug's "Direct molecular targets" uses, strongest-affinity first, each
    // row jumping to its target when browsable.
    if (m.ownBindings && m.ownBindings.length) {
      const bul = el("ul", "metab-bindings");
      const mbinds = [...m.ownBindings].sort((a, b) => bindingKi(a) - bindingKi(b));
      for (const b of mbinds) {
        const tgt = targetById.get(b.target);
        const onActivate = tgt && tgt.focusable ? () => onTargetPick(tgt) : null;
        bul.appendChild(bindingRow(b, drug, b.targetName, onActivate));
      }
      li.appendChild(bul);
    }
    ul.appendChild(li);
  }
  metaEl.appendChild(ul);
  return { sec: metaEl, flash: flashLi };
}
