// Per-target BETA annotations: receptor effects (+ the effect index), release
// modulation, demographics and genetic variants.

import { resolveEffects, readEffectIndex } from "../receptor-effects.js";
import { resolveModulation } from "../release-modulation.js";
import { resolveDemographics } from "../receptor-demographics.js";
import { resolveVariants } from "../receptor-variants.js";
import { localize, localizeMap } from "./localize.js";
import { mapSources, mapUncertainty } from "./sources.js";

export function resolveTargetAnnotations({ targets, drugs, drugById, metaRecord, v }, effectIndex) {
  const { drugTargets } = v;
  // receptor_effect nodes (BETA): target id -> resolved effect rows, for the
  // receptor / target panel's Effects section and the drug panel's derived join
  // (js/receptor-effects.js). A receptor-linked target reads its receptor's record.
  const effectModes = Object.fromEntries(Object.entries(metaRecord.receptor_effect_modes || {})
    .map(([k, v]) => [k, { label: localize(v.label), actions: v.actions || [] }]));
  const effectLabels = localizeMap(metaRecord.receptor_effect_labels);
  const effectsByTarget = new Map();
  for (const tgt of targets) {
    const raw = tgt.receptor ? tgt.receptor.effects : (drugTargets[tgt.id] || {}).effects;
    const rows = resolveEffects(raw, effectModes, effectLabels)
      .map((e) => ({ ...e, sources: mapSources(e.sources), uncertainty: mapUncertainty(e.uncertainty) }));
    tgt.effectInfo = rows;
    // {searched, corpora} when every required corpus was searched and none states an
    // effect (tools/data_generators/unknown.py): the panel's blue UNKNOWN row. Never an
    // effect, so it stays out of effectsByTarget and the effect index.
    const owner = tgt.receptor || drugTargets[tgt.id] || {};
    tgt.effectsUnknown = rows.length ? null : owner.effects_unknown || null;
    if (tgt.receptor) {
      tgt.receptor.effectInfo = rows;
      tgt.receptor.effectsUnknown = tgt.effectsUnknown;
    }
    if (rows.length) effectsByTarget.set(tgt.id, rows);
  }
  // The effect-centred view of the same nodes (the Effects section + panel, BETA):
  // effect -> owners carrying it + drugs whose possible effects reach it, read from
  // the build-time index (the drug panel's possible effects come from it too).
  const effectRead = readEffectIndex(effectIndex, new Map(targets.map((tg) => [tg.id, tg])),
    effectsByTarget, new Map(drugs.map((d) => [d.id, d])), effectLabels);
  const effects = effectRead.effects
    .map((e) => ({ ...e, name: e.label, keywords: e.id.replace(/_/g, " ") }));
  const possibleEffectsByDrug = effectRead.byDrug;

  // receptor_release_modulation nodes (BETA): target id -> resolved rows, for the
  // receptor panel's Downstream section and the drug panel's derived release changes
  // (js/release-modulation.js). Receptors only: a release-modulation node sits on one.
  const rm = metaRecord.release_modulation || {};
  const modulationVocab = {
    kinds: localizeMap(rm.kinds),
    cells: localizeMap(rm.cells),
    transmitters: Object.fromEntries(Object.entries(rm.transmitters || {})
      .map(([k, v]) => [k, { label: localize(v.label), system: v.system }])),
  };
  const modulationByTarget = new Map();
  for (const tgt of targets) {
    if (!tgt.receptor) continue;
    const rows = resolveModulation(tgt.receptor.release_modulation, modulationVocab)
      .map((n) => ({ ...n, sources: mapSources(n.sources) }));
    tgt.receptor.modulationInfo = rows;
    tgt.modulationInfo = rows;
    if (rows.length) modulationByTarget.set(tgt.id, rows);
  }

  // receptor_demographic nodes (BETA): each target's "Across age and sex" rows
  // (js/receptor-demographics.js). A receptor-linked target reads its receptor's record.
  const dm = metaRecord.demographics || {};
  const demographicVocab = {
    factors: Object.fromEntries(Object.entries(dm.factors || {})
      .map(([k, v]) => [k, { label: localize(v.label) }])),
    glyphs: dm.glyphs || {},
  };
  for (const tgt of targets) {
    const raw = tgt.receptor ? tgt.receptor.demographics : (drugTargets[tgt.id] || {}).demographics;
    tgt.demographicInfo = resolveDemographics(raw, demographicVocab)
      .map((n) => ({ ...n, sources: mapSources(n.sources) }));
    if (tgt.receptor) tgt.receptor.demographicInfo = tgt.demographicInfo;
  }

  // receptor_variant nodes (ClinPGx #20): each target's "Genetic variants" rows
  // (js/receptor-variants.js). A receptor-linked target reads its receptor's record.
  const vv = metaRecord.variants || {};
  const variantVocab = {
    levels: Object.fromEntries(Object.entries(vv.levels || {})
      .map(([k, v]) => [k, { strength: localize(v.strength), label: localize(v.label) }])),
    categories: localizeMap(vv.categories),
    populations: localizeMap(vv.populations),
  };
  const drugNameOf = (id) => (drugById.get(id) || {}).name || null;
  for (const tgt of targets) {
    const raw = tgt.receptor ? tgt.receptor.variants : (drugTargets[tgt.id] || {}).variants;
    tgt.variantInfo = resolveVariants(raw, variantVocab, drugNameOf)
      .map((n) => ({ ...n, sources: mapSources(n.sources) }));
    if (tgt.receptor) tgt.receptor.variantInfo = tgt.variantInfo;
  }
  return { effectModes, effectsByTarget, effects, possibleEffectsByDrug, modulationByTarget };
}
