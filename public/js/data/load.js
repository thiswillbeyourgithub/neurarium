// Loading of the brain dataset produced by generate_data.py.
//
// The dataset is split by record type: data/meta.json (presentation maps),
// data/structures.jsonl, data/projections.jsonl and data/circuits.jsonl tell the
// viewer "what to draw" and "how things relate", and the data/shapes/*.json files
// are the source of "geometric form". This module fetches them all and returns a
// single normalized object so the rest of the app never has to know about the
// on-disk layout. The file a record lives in encodes its type (no `type` field).
//
// NOTE: because these are fetch()ed, the site must be served over http(s); see
// CLAUDE.md ("Running"). Opening index.html via file:// will fail CORS.
//
// Orchestration only: each stage lives in its own js/data/<stage>.js module and
// adds its slice to the dataset-so-far.
//
import { fetchOrThrow, fetchJsonl, derivedUrl } from "./fetch.js";
import { rehydrateQuotes } from "./quotes.js";
import { readVocab } from "./vocab.js";
import { mirrorProjections, resolveAnatomy, loadShapes, indexStructures } from "./anatomy.js";
import { resolveReceptors } from "./receptors.js";
import { makeToneRules, makeBindingResolver, borrowBindings } from "./bindings.js";
import { resolveDrugs } from "./drugs.js";
import { resolveMetabolites } from "./metabolites.js";
import { indexDrugsByTarget } from "./drug-index.js";
import { indexEnzymes } from "./pk.js";
import { buildTargets, indexTargetsByStructure } from "./targets.js";
import { resolveTargetAnnotations } from "./effects.js";
import { resolveAddons } from "./addons.js";

/**
 * Load and assemble the whole dataset: the per-type data files (meta.json +
 * structures/projections/circuits.jsonl) plus every referenced shape file, all
 * fetched in parallel.
 * @param {string} [dataDir="data"] Directory the data files live under.
 * @returns {Promise<import("../data.js").BrainData>}
 */
export async function loadBrainData(dataDir = "data", onProgress = null) {
  onProgress?.({ stage: "meta" });
  // The emitted data is English-only; the French translations live in a single
  // side table (data/translations.fr.json) that `window.__I18N__.pick` looks each
  // English string up in. Fetch + install it BEFORE any localize() runs, and ONLY
  // in French (English users never request it, and it stays an empty table). A
  // failed fetch is non-fatal: pick() then falls back to the English strings.
  if (window.__I18N__.lang === "fr") {
    try {
      const tr = await (await fetchOrThrow(`${dataDir}/translations.fr.json`)).json();
      window.__I18N__.setDataTranslations(tr);
    } catch (e) {
      console.error("Could not load French translations; showing English data.", e);
    }
  }
  const [metaRecord, structures, projections, circuits, projectionGroups,
         receptors, drugs, metaboliteRecords, addonRecords, quotes, effectIndex] =
    await Promise.all([
      fetchOrThrow(`${dataDir}/meta.json`).then((r) => r.json()),
      fetchJsonl(`${dataDir}/structures.jsonl`),
      fetchJsonl(`${dataDir}/projections.jsonl`),
      fetchJsonl(`${dataDir}/circuits.jsonl`),
      fetchJsonl(`${dataDir}/projection_groups.jsonl`),
      fetchJsonl(`${dataDir}/receptors.jsonl`),
      fetchJsonl(`${dataDir}/drugs.jsonl`),
      fetchJsonl(`${dataDir}/metabolites.jsonl`),
      fetchJsonl(`${dataDir}/addons.jsonl`),
      fetchJsonl(`${dataDir}/quotes.jsonl`),
      // The effect index is built at deploy / serve time, never committed (see
      // tools/data_generators/effect_index.py). Non-fatal: the viewer still works
      // without it, the red banner says what is missing.
      fetchOrThrow(derivedUrl(dataDir, "effects.json")).then((r) => r.json()).catch((e) => {
        console.error("Could not load the effect index.", e);
        window.showErrorBanner?.(window.__I18N__.t("effects.loadError", { msg: e.message }));
        return null;
      }),
    ]);
  // Source quotes are emitted once into quotes.jsonl (deduplicated), each node
  // carrying only a `{quote_id, provenance}` reference (see quote_table.py).
  // Rehydrate every reference in place BEFORE any downstream use, so the rest of
  // the viewer sees each source with its `corpus`/`page`/`quote`/`species` fields
  // as if they had been emitted inline. The `provenance` grade stays on the node.
  const quotesById = Object.create(null);
  for (const q of quotes) quotesById[q.id] = q;
  rehydrateQuotes([metaRecord, structures, projections, circuits,
                   projectionGroups, receptors, drugs, metaboliteRecords, addonRecords],
                  quotesById);
  // A metabolite is ONE record per molecule (metabolites.jsonl: name, drug_id, own T½,
  // own bindings), referenced by id from each parent's metabolites[] (`{id, sources,
  // formed_by}`: the per-parent claims). Join them here, before any downstream use, so
  // the rest of the viewer sees each parent's metabolite with the molecule's fields;
  // the molecule's arrays stay shared objects across parents (nordazepam's bindings
  // are one array under diazepam, clorazepate, prazepam and chlordiazepoxide).
  const metaboliteById = new Map(metaboliteRecords.map((m) => [m.id, m]));
  for (const d of drugs) {
    d.metabolites = (d.metabolites || []).map((ref) => ({ ...metaboliteById.get(ref.id), ...ref }));
  }
  mirrorProjections(projections);
  // Surface the loaded meta immediately (before the slower shape fetch + SDF
  // meshing): the loading gate's sourcing popup fills its coverage bars from
  // metaRecord.provenance_stats, so they show while the brain is still meshing.
  onProgress?.({ stage: "meta-ready", meta: metaRecord });

  const v = readVocab(metaRecord);
  const ds = { metaRecord, structures, projections, circuits, projectionGroups,
               receptors, drugs, v };
  const projectionGroupsByKey = resolveAnatomy(ds);
  await loadShapes(structures, onProgress);
  Object.assign(ds, indexStructures(structures));
  const { byId } = ds;
  resolveReceptors(ds);
  const tone = makeToneRules(receptors, metaRecord);
  const bindingDisplayFields = makeBindingResolver(v);
  borrowBindings(drugs);
  resolveDrugs(ds, tone, bindingDisplayFields);
  ds.drugById = resolveMetabolites(ds, bindingDisplayFields);
  const { drugsByTarget, prodrugsByTarget } = indexDrugsByTarget(drugs);

  const { enzymes, drugsByEnzyme, pkInteractionsOf } = indexEnzymes(ds);
  const targets = ds.targets = buildTargets(ds);
  const { effectModes, effectsByTarget, effects, possibleEffectsByDrug, modulationByTarget } =
    resolveTargetAnnotations(ds, effectIndex);
  const targetsByStructure = indexTargetsByStructure(ds);
  const { addons, addonsBySlot } = resolveAddons(ds, addonRecords);
  const { projectionColors, signColors, groupLabels, kindLabels, signLabels,
          receptorFamilyLabels, receptorFamilyColors, receptorClassLabels,
          synapticLabels, targetTypeLabels, targetTypeColors, drugCategoryLabels,
          drugEffectColors, drugEffectLabels, systemFlowKinds, sourceCorpora,
          densityMinReliability, provenanceStats, addonSlots, addonTones,
          quotePipelines } = v;

  return {
    structures,
    projections,
    circuits,
    projectionGroups,
    projectionGroupsByKey,
    receptors,
    targets,
    targetsByStructure,
    drugs,
    drugsByTarget,
    prodrugsByTarget,
    enzymes,
    drugsByEnzyme,
    pkInteractionsOf,
    addons,
    addonsBySlot,
    effectsByTarget,
    effects,
    possibleEffectsByDrug,
    modulationByTarget,
    byId,
    meta: {
      projectionColors,
      groupLabels,
      kindLabels,
      systemFlowKinds,
      signColors,
      signLabels,
      receptorFamilyLabels,
      receptorFamilyColors,
      receptorClassLabels,
      synapticLabels,
      targetTypeLabels,
      targetTypeColors,
      drugCategoryLabels,
      drugEffectColors,
      drugEffectLabels,
      sourceCorpora,
      densityMinReliability,
      provenanceStats,
      addonSlots,
      addonTones,
      // Per-bucket share of a tone (see toneBySystem); the drug panel's caption names it.
      toneFactors: tone.toneFactors,
      quotePipelines,
      effectModes,
    },
  };
}
