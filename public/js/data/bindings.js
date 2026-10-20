// Drug-binding resolution shared by drugs and metabolites: the tone-rule join, the
// display + provenance fields of one binding, and the borrowed-bindings passes.

import { normName } from "../util.js";
import { localize } from "./localize.js";
import { strongestGrade } from "../grades.js";
import { mapSources, mapUncertainty } from "./sources.js";

/** The tone-rule lookups over meta.tone_rules / tone_factors (see toneBySystem). */
export function makeToneRules(receptors, metaRecord) {
  // Receptor sign/synaptic, used to detect a presynaptic inhibitory autoreceptor
  // (an alpha2 / D2/D3 / 5-HT1A-B-D): agonising it lowers its system's tone,
  // blocking it raises it. Postsynaptic receptors are NOT tone-setters (dots only).
  const receptorMeta = new Map(receptors.map((r) => [r.id, { sign: r.sign, synaptic: r.synaptic }]));
  // The "tone-setters + autoreceptors" flow model. Direction comes from target type +
  // action (+ the autoreceptor sign for presynaptic receptors), NOT from receptor
  // class (a postsynaptic gain claim we deliberately do not make). The rule table is
  // authored once in tools/data_generators/drugs.py and shipped as meta.tone_rules.
  const toneRules = metaRecord.tone_rules || {};
  // Which tone bucket a binding falls in (see meta.tone_rules): the join the rule
  // table cannot express, since it needs the target's type + vesicular flag and, for
  // the autoreceptor case, the receptor record behind the binding.
  const toneBucketOf = (tgt) => {
    const type = tgt.type || "";
    if (type === "transporter") {
      return tgt.vesicular ? "vesicular_transporter" : "transporter";
    }
    if (type === "enzyme" || type === "vesicle_protein") return type;
    if (type === "receptor" || type === "receptor_group") {
      // Sign/synaptic from the specific receptor record (a modeled 5-HT1x / D2/D3),
      // else from the group's own flag (the α2 family, carried in meta.drug_targets).
      const rm = tgt.receptor ? receptorMeta.get(tgt.receptor) : tgt;
      const presyn = rm && (rm.synaptic === "presynaptic" || rm.synaptic === "both");
      // Only a presynaptic INHIBITORY receptor feeds back on release; every other
      // receptor binding stays dots-only and draws no flow.
      if (presyn && rm.sign === "inhibitory") return "autoreceptor";
    }
    return null;
  };
  // The signed tone one binding sets: +1 raises the transmitter's tone, -1 lowers it,
  // 0 = not a tone setter. The rule table itself is DATA (meta.tone_rules, authored in
  // tools/data_generators/drugs.py), so this and check_data.py's _tone_of read one
  // source of truth instead of each transcribing it.
  const toneRuleEntry = (tgt, action) => {
    const bucket = toneBucketOf(tgt);
    return (bucket && (toneRules[bucket] || {})[action]) || null;
  };
  const toneSignOf = (tgt, action) => (toneRuleEntry(tgt, action) || [0])[0];
  const toneRuleOf = (tgt, action) => (toneRuleEntry(tgt, action) || [0, null])[1];
  // The bucket's share relative to a reuptake block (meta.tone_factors, default 1).
  const toneFactors = metaRecord.tone_factors || {};
  const toneFactorOf = (tgt) => toneFactors[toneBucketOf(tgt)] ?? 1;
  return { toneSignOf, toneRuleOf, toneFactorOf, toneFactors };
}

/** The shared binding resolver (bindingDisplayFields), closed over the vocab. */
export function makeBindingResolver(v) {
  const { sourceCorpora, drugTargets, drugActions, drugEffectColors, drugEffectLabels } = v;
  // A binding's measured PDSP Ki -> the display object the drug panel renders beside
  // the binding (value + range + human/non-human counts, its own verified badge, and
  // the exact representative assay for the tooltip). `mapped` flags a value borrowed
  // through the alias map (an enantiomer/prodrug/metabolite), so the panel warns
  // which compound it was actually measured on. Null when the binding has no Ki.
  const resolveKi = (ki) => {
    if (!ki) return null;
    const src = ki.source || {};
    const corpus = sourceCorpora[src.corpus] || {};
    return {
      median: ki.median, min: ki.min, max: ki.max,
      nHuman: ki.n_human || 0, nNonhuman: ki.n_nonhuman || 0,
      inactive: ki.inactive || 0,
      provenance: src.provenance || null,
      // The Ki source corpus: a CSV assay corpus (pdsp_ki) reports per-assay
      // species counts + a representative row; a quote-gated literature corpus
      // (wikipedia_pharm) reports a single value with no assay counts, so the panel
      // renders it as a literature Ki (no human/non-human line, no "measured in X").
      corpus: src.corpus || "",
      kiId: src.ki_id != null ? src.ki_id : null,
      valueNm: src.value_nm != null ? src.value_nm : null,
      species: src.species || "", preparation: src.preparation || "",
      radioligand: src.radioligand || "", reference: src.reference || "",
      corpusRef: corpus.ref || src.corpus, corpusUrl: corpus.url || "",
      mapped: !!src.mapped, measuredAs: src.measured_as || "",
      relation: src.relation || "", pdspNames: src.pdsp_names || [],
      fetched: src.fetched || null,
      licence: src.licence || null,
    };
  };
  // Resolve the display + provenance fields of a binding, shared by a drug's own
  // bindings and a metabolite's inline bindings (the receptor "Interacting drugs"
  // row reads exactly these). It deliberately OMITS the animation fields
  // (structureIds / flowKind / affinityWeight / toneSign): those drive the 3D
  // overlay, which only a focusable drug plays, so the drug loop adds them on top.
  // Returns the resolved target dict as `tgt` too, so the drug loop reuses it for
  // structureIds/flow without a second lookup (the metabolite path drops it).
  const bindingDisplayFields = (b) => {
    const tgt = drugTargets[b.target] || {};
    const affinityOnly = !!b.affinity_only;
    // The source says this one happens outside the brain (carbidopa at DDC,
    // entacapone at COMT). It keeps its action, effect colour and source, but the
    // drug loop below leaves it out of the lit regions and the flow, since the
    // dataset models no periphery to light.
    const peripheral = !!b.peripheral;
    const act = affinityOnly ? {} : drugActions[b.action] || {};
    const effect = affinityOnly ? null : b.effect || act.effect || "modulate";
    return {
      tgt,
      affinityOnly,
      peripheral,
      effect,
      target: b.target,
      targetName: tgt.name ? localize(tgt.name) : b.target,
      system: tgt.system || null,
      receptor: tgt.receptor || null,
      action: affinityOnly ? null : b.action,
      actionLabel: affinityOnly ? null : act.label ? localize(act.label) : b.action,
      effectColor: affinityOnly ? null : drugEffectColors[effect] || "#ffffff",
      effectLabel: affinityOnly ? null : drugEffectLabels[effect] || effect,
      note: b.note ? localize(b.note) : "",
      tentative: !!b.tentative,
      sources: mapSources(b.sources),
      provenance: strongestGrade([
        ...(b.sources || []),
        ...(b.ki && b.ki.source ? [b.ki.source] : []),
      ]),
      // The DIRECTION is its own node (kind `drug_binding_action`), so it is graded
      // from the quote sources ALONE: a Ki attests that the ligand binds the target,
      // never whether it activates or blocks it. null = no direction claim at all
      // (affinity_only), which the panel and the browser render as NOSOURCE.
      // "unknown" = every required source was searched and none states the direction
      // (a recorded search, tools/data_generators/unknown.py): its own pill, not NOSOURCE.
      actionProvenance: affinityOnly
        ? (b.unknown ? "unknown" : null)
        : strongestGrade(b.sources) || "llm",
      // {searched, corpora} of that search, for the pill's tooltip; null otherwise.
      unknown: affinityOnly && b.unknown ? b.unknown : null,
      // Reasons this claim's source does not attribute it (the orange "uncertain"
      // badge, derived in tools/data_generators/quotes/uncertainty.py). Empty for all
      // but the flagged bindings. See mapUncertainty.
      uncertainty: mapUncertainty(b.uncertainty),
      ki: resolveKi(b.ki),
    };
  };
  return bindingDisplayFields;
}

/** Prodrugs and salts borrow their metabolites' / constituents' raw bindings. */
export function borrowBindings(drugs) {
  // A prodrug (node kind drug_prodrug) is inactive itself and carries no binding of
  // its own (bar the activating enzyme it is the substrate of, levodopa at AADC, kept
  // first), yet focusing it should light what its active metabolite hits. So before
  // the loop resolves bindings, it borrows each metabolite's raw bindings (its own
  // `bindings[]`, else its linked modeled drug's), tagged `via_metabolite`: the scene,
  // flow and "Pharmacodynamics: binding profile" treat them like the drug's, while every list that counts a
  // binding node once (receptor panels, node browser, simulation) skips the tag,
  // since the metabolite already owns that node. Runs on raw records, before any
  // drug's bindings are mapped.
  const rawDrugById = new Map(drugs.map((d) => [d.id, d]));
  // A salt declaring `constituents` (node kind drug_constituents: dimenhydrinate IS
  // diphenhydramine + 8-chlorotheophylline) borrows each MODELED constituent's raw
  // bindings the same way, under the same tag (it names the molecule lent from, so the
  // panel reads "via Diphenhydramine"); an unmodeled constituent lends nothing.
  // Mirrored for the agent surface by data_generators/effect_index.py drug_bindings.
  const rawDrugByNorm = new Map(drugs.map((d) => [normName(d.name), d]));
  for (const d of drugs) {
    for (const name of d.constituents || []) {
      const part = rawDrugById.get(name.toLowerCase()) || rawDrugByNorm.get(normName(name));
      if (!part || part === d) continue;
      d.bindings = (d.bindings || []).concat(
        (part.bindings || []).map((b) => ({ ...b, via_metabolite: name })));
    }
  }
  // Each active metabolite's raw bindings (its own `bindings[]`, else its linked
  // modeled drug's), tagged with the metabolite's name.
  const metaboliteBindings = (d) => (d.metabolites || []).flatMap((m) => {
    const linked = m.drug_id ? rawDrugById.get(m.drug_id) : null;
    const own = (m.bindings || []).length ? m.bindings : linked ? linked.bindings || [] : [];
    return own.map((b) => ({ ...b, via_metabolite: m.name }));
  });
  // A prodrug takes them as its own bindings. Any other drug keeps them apart, in
  // `metabolite_bindings`: its target list stays the parent's own, while the readouts
  // derived from bindings (tone, inferred effects, release changes) add them, each
  // labelled by the metabolite (resolveDrugs `allBindings`). Same rule as
  // data_generators/effect_index.py drug_bindings. Computed before any prodrug is
  // extended, so a prodrug never lends on rows it borrowed itself.
  const lent = new Map(drugs.map((d) => [d, metaboliteBindings(d)]));
  for (const d of drugs) {
    if (d.prodrug) d.bindings = (d.bindings || []).concat(lent.get(d));
    else d.metabolite_bindings = lent.get(d);
  }
}
