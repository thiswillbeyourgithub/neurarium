// Combos and active metabolites: constituent links, each parent's resolved
// metabolite rows, and the reverse "metabolite of" link. Returns drugById.

import { normName } from "../util.js";
import { localize } from "./localize.js";
import { strongestGrade, mapSources, mapUncertainty } from "./sources.js";

export function resolveMetabolites({ drugs, v }, bindingDisplayFields) {
  const { enzymeDefs, enzymeReactions } = v;
  // Combo drugs ("A + B", or "A-B" with an en/em dash): resolve the constituents to
  // our standalone drug ids where they exist, so the panel warns it is a combination
  // and links out to each part (interactions between them may exist). Read off the
  // name, since a co-formulation is normally named after its parts. A salt of two
  // molecules is marketed under an INN of its own instead (dimenhydrinate IS
  // diphenhydramine + 8-chlorotheophylline), and is the reason a drug may state its
  // `constituents` explicitly: the name is then the drug's, not a list of its parts.
  const drugIdSet = new Set(drugs.map((d) => d.id));
  const drugByNorm = new Map(drugs.map((d) => [normName(d.name), d.id]));
  for (const d of drugs) {
    const parts = (d.constituents && d.constituents.length) ? d.constituents
      : /[+–—]/.test(d.name || "")
      ? d.name.split(/\s*[+–—]\s*/).map((p) => p.trim()).filter(Boolean)
      : null;
    d.combo = parts
      ? parts.map((p) => ({
          name: p,
          drugId: drugIdSet.has(p.toLowerCase())
            ? p.toLowerCase()
            : drugByNorm.get(normName(p)) || null,
        }))
      : null;
  }

  // Resolve each drug's active metabolites. Link a metabolite that is itself a
  // modeled drug (by explicit drug_id, else by matching its name) so the panel can
  // reuse that drug's already-resolved bindings + T½ and jump to it (no duplication).
  // A metabolite keeps its OWN identity provenance (`sources`) and optional own T½;
  // its inline `bindings` (a non-modeled metabolite's own Wikipedia/PDSP-sourced
  // receptor bindings) are resolved for display via the shared bindingDisplayFields.
  const drugById = new Map(drugs.map((d) => [d.id, d]));
  // A molecule's own bindings, resolved ONCE per metabolite id and shared by every
  // parent's row (so a target panel deduping by identity sees one molecule).
  const ownBindingsById = new Map();
  for (const d of drugs) {
    d.metabolites = (d.metabolites || []).map((m) => {
      const linkedId = m.drug_id || drugByNorm.get(normName(m.name)) || null;
      const linked = linkedId ? drugById.get(linkedId) || null : null;
      if (!ownBindingsById.has(m.id)) {
        ownBindingsById.set(m.id, (m.bindings || []).map((b) => {
          // Drop the resolver's `tgt` scratch field; keep only display/provenance.
          const { tgt, ...disp } = bindingDisplayFields(b);
          void tgt;
          return disp;
        }));
      }
      const ownBindings = ownBindingsById.get(m.id);
      // Which enzyme(s) MADE this metabolite: the mirror of d.enzymes above (there the
      // drug is the substrate, here the metabolite is the product), so it reuses the
      // same meta.enzymes labels and gets a `direction` of 0 (forming a metabolite says
      // nothing about the enzyme's throughput, so it never feeds a PK interaction edge).
      const formedBy = (m.formed_by || []).map((f) => {
        const def = enzymeDefs[f.enzyme] || {};
        return {
          ...f,
          label: def.label || f.enzyme,
          wikipedia: def.wikipedia || null,
          reactionLabel: enzymeReactions[f.reaction]
            ? localize(enzymeReactions[f.reaction]) : null,
          sources: mapSources(f.sources),
          provenance: strongestGrade(f.sources),
          uncertainty: mapUncertainty(f.uncertainty),
        };
      });
      return {
        id: m.id,
        // A metabolite that IS a modeled drug shows under that drug's label, so the
        // reader sees it is the same molecule (risperidone's "Paliperidone
        // (9-OH-risperidone)" row is the paliperidone drug).
        name: linked ? linked.label || linked.name : m.name,
        drugId: linkedId,
        formedBy,
        // Whether the link points at a standalone, clickable drug (so we can jump to
        // it AND avoid re-listing it under a receptor where it already appears).
        linkFocusable: !!(linked && linked.focusable),
        // Own inline bindings for the receptor row; else the linked drug's resolved
        // bindings (a metabolite-that-is-a-drug surfaces its targets for free).
        bindings: ownBindings.length ? ownBindings : linked ? linked.bindings : [],
        ownBindings,
        halfLife: m.half_life || (linked ? linked.halfLife : null),
        halfLifeSources: mapSources(m.half_life_sources),
        halfLifeProvenance: strongestGrade(m.half_life_sources),
        sources: mapSources(m.sources),
        provenance: strongestGrade(m.sources),
        // Another corpus denies the metabolite is active (quotes/contradictions.py).
        uncertainty: mapUncertainty(m.uncertainty),
      };
    });
  }

  // The reverse of a linked metabolite: on the metabolite drug's own panel, which
  // drugs it is the active metabolite of (paliperidone -> risperidone), each with
  // the parent's sourced metabolite entry so the claim keeps its pill.
  for (const d of drugs) {
    for (const m of d.metabolites) {
      const child = m.drugId && drugById.get(m.drugId);
      if (!child || child === d) continue;
      (child.metaboliteOf ||= []).push({ parent: d, sources: m.sources,
                                         provenance: m.provenance, uncertainty: m.uncertainty });
    }
  }
  return drugById;
}
