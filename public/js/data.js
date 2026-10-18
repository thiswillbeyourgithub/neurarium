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
import { resolveEffects, readEffectIndex } from "./receptor-effects.js";
import { resolveModulation } from "./release-modulation.js";
import { resolveDemographics } from "./receptor-demographics.js";
import { resolveVariants } from "./receptor-variants.js";

// Repeat-visit speed/offline resilience for these files is handled by the service
// worker (stale-while-revalidate for /data/*, see public/sw.js), not here.

/**
 * Parse JSONL text (one JSON object per line) into an array, skipping blank
 * lines. Kept tiny and dependency-free on purpose.
 * @param {string} text
 * @returns {object[]}
 */
function parseJsonl(text) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => JSON.parse(line));
}

/**
 * Fetch a URL and throw a descriptive error on a non-2xx response so failures
 * surface clearly in eruda instead of as silent `undefined`s downstream.
 * @param {string} url
 * @returns {Promise<Response>}
 */
async function fetchOrThrow(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to load ${url}: ${res.status} ${res.statusText}`);
  }
  return res;
}

/**
 * Fetch a JSONL file and parse it into an array of records.
 * @param {string} url
 * @returns {Promise<object[]>}
 */
async function fetchJsonl(url) {
  return parseJsonl(await (await fetchOrThrow(url)).text());
}

/**
 * A source's reference line with its download date appended, for a page of an
 * editable online corpus (Wikipedia, PDSP, GtoPdb, ...: the `fetched` date stamped by
 * tools/data_generators/freshness.py). A book page carries no date and keeps `ref`
 * as is. `tr` is the i18n `t()`, injected so this stays pure (and node-testable).
 * @param {string} ref       e.g. "Wikipedia (EN), p. vortioxetine"
 * @param {string} fetched   e.g. "2026-10-11", or falsy
 * @param {Function} tr      (key, vars) -> localized string
 * @returns {string}         e.g. "Wikipedia (EN), p. vortioxetine, downloaded 2026-10-11"
 */
export function withFetched(ref, fetched, tr) {
  return fetched ? `${ref}, ${tr("info.sourceFetched", { date: fetched })}` : ref;
}

/**
 * Rehydrate externalized source quotes in place. The emitted data replaces every
 * quote-bearing source with a `{quote_id, provenance}` reference and stores the
 * excerpt once in quotes.jsonl (see quote_table.py). This deep-walk merges every
 * field of the quote node except its `id` (`corpus`, `page`, `quote`, `species`,
 * `llm`, `heading`, `fetched`, ...) back onto each reference, so downstream code
 * reads `source.quote` etc. exactly as before, and a field the generator adds to the
 * quote node needs no edit here (check_data.py's rehydrate_quotes copies the same
 * way). A dangling `quote_id` (no matching quote) is left as-is (check_data.py
 * guards against it).
 * @param {*} node       Any value (object/array/scalar) to walk.
 * @param {object} byId  quote_id -> quote node map.
 */
export function rehydrateQuotes(node, byId) {
  if (Array.isArray(node)) {
    for (const v of node) rehydrateQuotes(v, byId);
  } else if (node && typeof node === "object") {
    if (typeof node.quote_id === "string") {
      const q = byId[node.quote_id];
      if (q) {
        for (const k in q) if (k !== "id") node[k] = q[k];
      }
    }
    for (const k in node) rehydrateQuotes(node[k], byId);
  }
}

/**
 * Resolve a data string to the chosen language. The emitted data is English-only
 * (see generate_data.py's `externalize`); `window.__I18N__.pick` swaps in the
 * French side-table translation when the visitor reads French. js/i18n.js is a
 * classic script that runs before every module, so `__I18N__` is always there.
 * @param {string} field
 * @returns {string}
 */
function localize(field) {
  return window.__I18N__.pick(field);
}

/**
 * @typedef {Object} BrainData
 * @property {object[]} structures  Region records (from structures.jsonl), each
 *   augmented with a resolved `shape` payload from its data/shapes/<id>.json file.
 *   `name`/`base_name` are localized to plain strings (the full hemisphere name
 *   and the side-stripped legend label).
 * @property {object[]} projections Directed pathway records (from projections.jsonl),
 *   each augmented with a resolved `color` (from the kind->colour meta map) plus a
 *   `sign` (excitatory/inhibitory/modulatory) and its `signColor` for the coarse
 *   colour mode; its `label`/`description`/`neurotransmitter` are localized to
 *   plain strings.
 * @property {object[]} circuits    Named circuit records (from circuits.jsonl):
 *   `{id, name, structures:[structure ids]}` (localized `name`), plus an optional
 *   localized `description` + `sources`/`provenance`. The arrows belonging to a
 *   circuit are derived in the viewer (both endpoints among `structures`).
 * @property {object[]} projectionGroups  Projection-group records (from
 *   projection_groups.jsonl): one per legend pathway row, in both colour modes
 *   (`mode:"kind"|"sign"`, `key` the kind/sign). Each has a localized `name` +
 *   `description`, `sources`/`provenance`, optional `wikipedia`. Member pathways
 *   are derived in the viewer (the projections whose kind/sign matches `key`).
 * @property {Map<string,object>} projectionGroupsByKey  `${mode}:${key}` -> the
 *   projection-group record, so a legend row resolves its data by its grouping.
 * @property {object[]} receptors  Neurotransmitter receptor records (from
 *   receptors.jsonl). Each is augmented with localized `neurotransmitter` /
 *   `description`, a resolved `familyLabel` / `classLabel` / `signLabel` /
 *   `synapticLabel` and `signColor`, the concrete `structureIds` its `locations`
 *   bases expand to (every structure when `ubiquitous`), the side-stripped
 *   `locationNames`, and a `focusable` flag (false for the inert "stub" receptors).
 *   Its raw `classification` object passes through: one graded sub-claim per
 *   attribute (`family` / `receptor_class` / `sign` / `synaptic`), each with its own
 *   `grade` (+ optional `sources`), shown as that fact row's own provenance pill so
 *   an unsourced attribute reads honestly instead of borrowing a neighbour's grade.
 * @property {object[]} targets  The merged "Receptors & targets" browse list: one
 *   normalized, focusable entry per thing a drug acts on. Each carries `id`,
 *   `kind` ("receptor" or a non-receptor type: transporter / enzyme / ion_channel /
 *   vesicle_protein / receptor_group), `name`, `system` (grouping family, or null),
 *   `swatchColor`, `structureIds`, `focusable` + `keywords`. A "receptor" entry
 *   points back at its receptor record (`receptor`); a non-receptor one adds
 *   `typeLabel` / `systemLabel` / `wikipedia` / `locationNames` (+ the parallel
 *   `locationBases` base ids, so each panel region row can jump to its structure).
 * @property {Map<string, object[]>} targetsByStructure  The reverse expression index:
 *   region base id -> `{target, info, ubiquitous}` for every target expressed there,
 *   `info` being that region's own graded expression node (the same one the receptor
 *   panel's "Found in" row shows). Lets a structure panel answer "what sits here?".
 * @property {object[]} drugs  Drug records (from drugs.jsonl, sourced from Stahl's
 *   Prescriber's Guide). Each is augmented with localized `description` / `nbn`,
 *   `categoryLabels` (+ primary `category`), and resolved `bindings` (each binding
 *   carrying `targetName`, `actionLabel`, net `effect` + `effectColor`/`effectLabel`,
 *   localized `note`, an `affinityWeight` (0.35..1, Ki-derived engagement) + signed
 *   `toneSign`, and the concrete `structureIds` it lights), the union
 *   `structureIds` the focus dims to, `flowSystems` (kind -> {direction, weight},
 *   the signed affinity-weighted per-system flow tone), a `focusable` flag and search `keywords`,
 *   plus a `structureImage` (the vendored molecular-structure SVG path, or null).
 * @property {object[]} enzymes  The Enzymes browse list: one entry per metabolic
 *   isoform some drug actually touches, `{id, label, wikipedia, rows, metabolites,
 *   keywords}` where `rows` are its `{drug, enzyme}` role pairs and `metabolites` its
 *   `{drug, metabolite, formedBy}` triples (the active metabolites it forms).
 *   Pharmacokinetics, so an entry has no anatomy and never lights the scene.
 * @property {object[]} effects  The Effects browse list (BETA): one entry per
 *   receptor_effect some target carries, `{id, label, name, owners, drugs, keywords}`,
 *   read from the build-time `derived/effects.json` (`readEffectIndex`,
 *   js/receptor-effects.js); `drugs` is derived, never stored. Empty when that fails to load.
 * @property {Map<string, object[]>} possibleEffectsByDrug  drug id -> its possible
 *   effects `{effect, label, via}` from the same file (the drug panel's derived section).
 * @property {Map<string, {drug: object, enzyme: object}[]>} drugsByEnzyme  Reverse
 *   index: enzyme id -> the drugs with a role at it, each paired with that role row.
 * @property {(drug: object) => {affects: object[], affectedBy: object[]}} pkInteractionsOf
 *   The drug -> drug pharmacokinetic edges implied by those roles (an inhibitor or
 *   inducer of an enzyme meets its substrates). Derived on demand, never authored;
 *   one entry per (other drug, direction), naming every enzyme the pair shares.
 * @property {Map<string, {drug: object, binding: object}[]>} drugsByTarget
 *   Reverse index: a target id (a receptor id or a drug_targets key, matching each
 *   `targets` entry's id) -> the drugs that act on it, each paired with its resolved
 *   binding (its net-effect colour + action), deduped to one row per (drug, target).
 *   Lets a receptor / target panel list its interacting drugs grouped by category.
 * @property {Map<string, {drug: object, binding: object}[]>} prodrugsByTarget
 *   Same shape, for a prodrug's borrowed bindings (`binding.viaMetabolite` set):
 *   listed in a target panel "via" their metabolite drug, never counted.
 * @property {object[]} addons  Addon records (from addons.jsonl): sourced
 *   annotations that carry their own insertion point, each `{id, ownerKind, owner,
 *   slot, display, tone, glyph, title, text, sources, provenance}` plus the resolved
 *   `ownerName` + `focus` ({nav, arg}) of the node it annotates. The claim is in
 *   `text`; `slot` says which panel hook draws it (see meta.addonSlots).
 * @property {Map<string, object[]>} addonsBySlot  Reverse index:
 *   `${ownerKind}:${owner}:${slot}` -> the addons a panel should splice in there.
 * @property {Map<string, object>} byId  structure id -> structure record.
 * @property {{projectionColors: Object<string,string>,
 *   groupLabels: Object<string,string>,
 *   kindLabels: Object<string,string>,
 *   systemFlowKinds: Object<string,string>,
 *   signColors: Object<string,string>,
 *   signLabels: Object<string,string>}} meta  Presentation maps emitted by the
 *   generator (kind->arrow colour, group->legend heading, kind->display label,
 *   transmitter-system->flow-overlay projection kind, and the excit/inhib sign
 *   colour + heading for the colour-mode toggle), so the dataset is self-describing
 *   rather than relying on hardcoded values in the viewer.
 *   `groupLabels`/`kindLabels`/`signLabels` are localized to plain strings.
 */

// Fold a drug / metabolite name for joining ("Desmethyldiazepam (nordazepam)" ->
// "desmethyldiazepamnordazepam").
const normName = (s) => (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

const AFFINITY_DEFAULT = 0.55;
/**
 * Relative engagement of one binding from its measured Ki (NOT an effect size):
 * 0.35 at Ki >= 1 uM, rising with pKi to 1 at Ki <= 0.1 nM; AFFINITY_DEFAULT without
 * a Ki. Weighs the dot cloud and the binding's share of its system's tone.
 * @param {{median:number}|null} ki
 */
export function affinityWeightOf(ki) {
  const t = kiRamp(ki);
  return t === null ? AFFINITY_DEFAULT : 0.35 + 0.65 * t;
}

// pKi ramp shared by both weights: 0 at Ki >= 1 uM, 1 at Ki <= 0.1 nM, null without a Ki.
function kiRamp(ki) {
  if (!ki || !(ki.median > 0)) return null;
  const pKi = 9 - Math.log10(ki.median); // median is in nM
  return Math.max(0, Math.min(1, (pKi - 6) / 4));
}

const TONE_WEIGHT_NO_KI = 0.5;
/**
 * A binding's weight in its system's indicative tone: the bare pKi ramp, 0 at
 * Ki >= 1 uM up to 1 at Ki <= 0.1 nM, TONE_WEIGHT_NO_KI (a 10 nM binding) without a
 * Ki. No floor, unlike affinityWeightOf (whose floor keeps a weak binding's dots
 * visible): with one, several micromolar hits summed past a sub-nanomolar one.
 * @param {{median:number}|null} ki
 */
export function toneWeightOf(ki) {
  const t = kiRamp(ki);
  return t === null ? TONE_WEIGHT_NO_KI : t;
}

/**
 * A drug's indicative tone per transmitter system (the "Neurotransmitter tone"
 * section and the flow overlay): every tone-setting binding adds
 * `toneSign * toneFactor * toneWeight` to its system's sum; postsynaptic receptors carry
 * toneSign 0 and add nothing. A zero sum drops the system (opposing bindings cancel).
 * @param {object[]} bindings resolved bindings ({flowKind, toneSign, toneFactor, toneWeight})
 * @returns {Object<string, {direction:number, weight:number, sum:number,
 *   terms:object[]}>} per kind: sign of the sum, |sum| capped at 1, the raw sum, and
 *   the bindings that make it up (in binding order)
 */
export function toneBySystem(bindings) {
  const acc = new Map();
  for (const b of bindings) {
    if (!b.flowKind || !b.toneSign) continue;
    const e = acc.get(b.flowKind) || { sum: 0, terms: [] };
    e.sum += b.toneSign * (b.toneFactor ?? 1) * b.toneWeight;
    e.terms.push(b);
    acc.set(b.flowKind, e);
  }
  const out = {};
  for (const [kind, { sum, terms }] of acc) {
    if (!sum) continue;
    out[kind] = { direction: sum > 0 ? 1 : -1, weight: Math.min(1, Math.abs(sum)), sum, terms };
  }
  return out;
}

/**
 * Build the target reverse indexes off resolved drugs (each with `bindings`,
 * `metabolites` carrying `linkFocusable` + `ownBindings`, `displayName`). Pure, so
 * tools/tests/drugs_by_target.test.mjs drives it on hand-built drugs.
 * @returns {{drugsByTarget: Map, prodrugsByTarget: Map}} see BrainData.
 */
export function indexDrugsByTarget(drugs) {
  // Reverse index from the bindings: a target id -> the drugs that act on it, each
  // paired with its resolved binding (so the binding's net-effect colour + action
  // is available). The key is the binding's `target` (a receptor id or a
  // drug_targets key), which is exactly each "Receptors & targets" entry's id, so a
  // receptor / target panel can list "interacting drugs" by looking itself up here.
  // Deduped to one row per (drug, target) in case a drug binds the same target
  // twice (the first binding wins).
  const drugsByTarget = new Map();
  // One metabolite can be produced by several modeled drugs (e.g. mCPP by both
  // nefazodone and trazodone), so it would otherwise contribute a separate, identical
  // row per parent to the same target. We collapse those into ONE row keyed by
  // (metabolite id, target) and merge the parents into `viaMetaboliteOfList`,
  // so the panel reads "metab. of A, B" once instead of listing the same molecule
  // twice. Persists across the outer drug loop (a shared metabolite is visited under
  // each parent).
  const metabRowByKey = new Map();
  // A prodrug's borrowed bindings, kept apart from `drugsByTarget` so a target panel
  // can show "LISDEXAMFETAMINE (via dextroamphetamine)" without counting it: the
  // binding node is the metabolite's (see the prodrug pass above). Only a borrowing
  // through a focusable metabolite drug (or a salt's modeled constituent) lands here; a non-drug metabolite already
  // gets its own "NAME (metab. of PRODRUG)" row below, which names the prodrug.
  const prodrugsByTarget = new Map();
  // A salt lends its constituent's bindings under the same tag (see the borrowing
  // pass), so a modeled constituent counts as the lender too.
  const focusableMetabolite = (d, name) =>
    d.metabolites.some((m) => m.name === name && m.linkFocusable)
    || (d.combo || []).some((c) => c.name === name && c.drugId);
  for (const d of drugs) {
    const seen = new Set();
    const seenBorrowed = new Set();
    for (const b of d.bindings) {
      if (b.viaMetabolite) {
        if (seenBorrowed.has(b.target) || !focusableMetabolite(d, b.viaMetabolite)) continue;
        seenBorrowed.add(b.target);
        if (!prodrugsByTarget.has(b.target)) prodrugsByTarget.set(b.target, []);
        prodrugsByTarget.get(b.target).push({ drug: d, binding: b });
        continue;
      }
      if (seen.has(b.target)) continue;
      seen.add(b.target);
      if (!drugsByTarget.has(b.target)) drugsByTarget.set(b.target, []);
      drugsByTarget.get(b.target).push({ drug: d, binding: b });
    }
    // Surface a metabolite's OWN bindings under their target too, attributed to the
    // parent drug ("NAME (metab. of PRODRUG)"). Only its own (non-linked) bindings,
    // and only when the metabolite is not itself a focusable drug already listed here,
    // so nothing is double-listed.
    for (const m of d.metabolites) {
      if (m.linkFocusable) continue;
      for (const b of m.ownBindings) {
        const rowKey = `${m.id || normName(m.name)}:${b.target}`;
        const existing = metabRowByKey.get(rowKey);
        if (existing) {
          // Same metabolite, same target, different parent: merge the prodrug into the
          // existing row rather than adding a duplicate (one molecule, one record, so
          // its bindings are the same under every parent).
          if (!existing.viaMetaboliteOfList.includes(d.displayName)) {
            existing.viaMetaboliteOfList.push(d.displayName);
          }
          continue;
        }
        if (!drugsByTarget.has(b.target)) drugsByTarget.set(b.target, []);
        const row = {
          drug: d,
          binding: b,
          viaMetaboliteOfList: [d.displayName],
          metaboliteName: m.name,
        };
        metabRowByKey.set(rowKey, row);
        drugsByTarget.get(b.target).push(row);
      }
    }
  }
  return { drugsByTarget, prodrugsByTarget };
}

/**
 * Where a build-time derived file sits: `derived/` is the SIBLING of the data dir
 * (`data` -> `derived/effects.json`, `site/data` -> `site/derived/effects.json`), so a
 * viewer pointed at another data dir reads that dir's index, never the page's.
 * @param {string} dataDir
 * @param {string} name
 */
export function derivedUrl(dataDir, name) {
  const parent = dataDir.replace(/\/+$/, "").replace(/[^/]*$/, "");
  return `${parent}derived/${name}`;
}

/**
 * Load and assemble the whole dataset: the per-type data files (meta.json +
 * structures/projections/circuits.jsonl) plus every referenced shape file, all
 * fetched in parallel.
 * @param {string} [dataDir="data"] Directory the data files live under.
 * @returns {Promise<BrainData>}
 */
/**
 * The bilingual search table (data/search_names.fr.json, English name -> French
 * name, emitted by generate_data.py's search_names), as one lookup that answers in
 * BOTH directions: `other("Hippocampus")` -> "Hippocampe" and
 * `other("Hippocampe")` -> "Hippocampus". The search box appends that other-language
 * name to each row's keywords, so either spelling finds a row in either UI language.
 * Fetched lazily by the search popup, not at startup; a failed fetch resolves to a
 * lookup that knows nothing (search then simply stays monolingual).
 * @param {string} [dataDir="data"]
 * @returns {Promise<(name:string)=>string|undefined>}
 */
export async function loadSearchNames(dataDir = "data") {
  let enFr = {};
  try {
    enFr = await (await fetchOrThrow(`${dataDir}/search_names.fr.json`)).json();
  } catch (e) {
    console.error("Could not load the bilingual search names.", e);
  }
  const both = new Map(Object.entries(enFr));
  for (const [en, fr] of Object.entries(enFr)) if (!both.has(fr)) both.set(fr, en);
  return (name) => both.get(name);
}

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
  // A symmetric pathway is stored once carrying `mirror: true` (the emitted file
  // authors only the right-hemisphere record, avoiding a duplicate row per
  // pathway; see generate_data.py _projection_records). Reflect each such record
  // to the other hemisphere here (flip `_R` <-> `_L` on both endpoints) so the
  // rest of the viewer sees the full bilateral connectome as if both rows had
  // been emitted. A midline endpoint is left unchanged, so a half-midline pathway
  // mirrors only its lateralized end. Done before any downstream use (colours,
  // circuit membership, legends), so every consumer sees both hemispheres.
  const mirrorHemisphere = (id) =>
    id.endsWith("_R") ? id.slice(0, -2) + "_L"
      : id.endsWith("_L") ? id.slice(0, -2) + "_R"
        : id;
  for (const p of projections.slice()) {
    if (!p.mirror) continue;
    delete p.mirror;
    projections.push({ ...p, from: mirrorHemisphere(p.from), to: mirrorHemisphere(p.to) });
  }
  // Surface the loaded meta immediately (before the slower shape fetch + SDF
  // meshing): the loading gate's sourcing popup fills its coverage bars from
  // metaRecord.provenance_stats, so they show while the brain is still meshing.
  onProgress?.({ stage: "meta-ready", meta: metaRecord });

  // Presentation maps emitted by the generator (kind->arrow colour,
  // group->legend heading, kind->display label), so the palette/headings live in
  // the data, not hardcoded in the viewer. The label maps are bilingual {en,fr};
  // localize their values to plain strings here (the colour map is neutral).
  const projectionColors = metaRecord.projection_colors || {};
  // Sign (excitatory / inhibitory) colour mode: kind->sign fold + sign->colour.
  const kindSigns = metaRecord.kind_signs || {};
  const signColors = metaRecord.sign_colors || {};
  const localizeMap = (m) =>
    Object.fromEntries(Object.entries(m || {}).map(([k, v]) => [k, localize(v)]));
  const groupLabels = localizeMap(metaRecord.group_labels);
  const kindLabels = localizeMap(metaRecord.kind_labels);
  const signLabels = localizeMap(metaRecord.sign_labels);
  // Receptor legend maps (family heading, mechanism class, pre/post-synaptic
  // label). The per-receptor sign reuses signColors/signLabels above.
  const receptorFamilyLabels = localizeMap(metaRecord.receptor_family_labels);
  // Family -> swatch colour, language-neutral: the transmitter's own colour for a
  // view that colours by transmitter (the simulation's receptor bars).
  const receptorFamilyColors = metaRecord.receptor_family_colors || {};
  const receptorClassLabels = localizeMap(metaRecord.receptor_class_labels);
  const synapticLabels = localizeMap(metaRecord.synaptic_labels);
  // Non-receptor drug-target presentation: type -> {en,fr} tag (localized) and
  // type -> swatch/dot colour (neutral), for the merged "Receptors & targets"
  // section where transporters/enzymes/channels sit beside the receptors.
  const targetTypeLabels = localizeMap(metaRecord.target_type_labels);
  const targetTypeColors = metaRecord.target_type_colors || {};
  // Drug legend + animation maps (category headings, binding targets, actions,
  // and the net-effect swatch colours/labels). drugTargets / drugActions are kept
  // as raw maps (their `name`/`label` are localized per binding below); the colour
  // map is language-neutral.
  const drugCategoryLabels = localizeMap(metaRecord.drug_category_labels);
  // Regulatory history vocabularies (first approval + withdrawals): id -> label.
  const historyCountries = localizeMap(metaRecord.drug_history_countries);
  const historyScopes = new Set(metaRecord.drug_history_scopes || []);
  const historyAgencies = localizeMap(metaRecord.drug_history_agencies);
  const withdrawalReasons = localizeMap(metaRecord.drug_withdrawal_reasons);
  // Pre-prescription workup vocabularies (BDPM RCP #24): test / timing id -> label.
  const workupTests = localizeMap(metaRecord.workup_tests);
  const workupTimings = localizeMap(metaRecord.workup_timings);
  // Formulation release types (closed vocabulary, display order): id -> label.
  const releaseLabels = localizeMap(metaRecord.drug_releases);
  const drugTargets = metaRecord.drug_targets || {};
  const drugActions = metaRecord.drug_actions || {};
  const drugEffectColors = metaRecord.drug_effect_colors || {};
  const drugEffectLabels = localizeMap(metaRecord.drug_effect_labels);
  // Drug metabolism vocabularies (see ENZYMES in generate_data.py): the isoform
  // id -> {label, wikipedia} map, plus role and strength labels. Raw for the defs
  // (an isoform name is language-neutral), localized for the prose ones.
  const enzymeDefs = metaRecord.enzymes || {};
  const enzymeRoles = metaRecord.enzyme_roles || {};
  const enzymeStrengths = metaRecord.enzyme_strengths || {};
  const enzymeReactions = metaRecord.enzyme_reactions || {};
  // Drug target system -> projection kind, for the per-drug "by-mechanism flow"
  // overlay (only the diffuse ascending modulatory systems are mapped; see
  // generate_data.py SYSTEM_FLOW_KINDS). Language-neutral, applied per drug below.
  const systemFlowKinds = metaRecord.system_flow_kinds || {};
  // Source corpora (id -> {short, citation, url, pages_dir}) the per-claim binding
  // sources cite; the drug panel resolves a binding source's `corpus` to this for
  // its tooltip ref (see SOURCE_CORPORA in generate_data.py). Raw map (citation is
  // language-neutral); pages_dir is author-side and ignored by the viewer.
  const sourceCorpora = metaRecord.source_corpora || {};
  // Cross-donor-agreement floor a density profile had to clear to be published, so the
  // panel can state the real threshold rather than restate the generator's constant.
  const densityMinReliability = metaRecord.density_min_reliability ?? null;
  // Programmatic sourcing tally (per kind + headline) for the About panel; passed
  // through as-is (the numbers are computed in generate_data.py, see
  // _provenance_stats). Null on a dataset that predates it.
  const provenanceStats = metaRecord.provenance_stats || null;
  // Addon-node hook registry: slot -> the node kind whose panel it belongs to, and
  // tone -> its glyph. The viewer renders addons generically off these rather than
  // knowing any slot by name, so a new hook is a generator edit plus one call site.
  const addonSlots = metaRecord.addon_slots || {};
  // The browse sections an addon may anchor instead of a node (key -> label): the
  // one owner kind that is a view rather than a datum, for a caveat true of a whole
  // collection at once (see addonOwner below).
  const addonSections = metaRecord.addon_sections || {};
  const addonTones = metaRecord.addon_tones || {};
  // How a quote came to be cited: pipeline key -> its chain of custody as ordered step
  // keys, rendered at the bottom of every source tooltip. Passed through as-is; the
  // viewer only joins and localizes, so a new pipeline never needs a viewer edit.
  const quotePipelines = metaRecord.quote_pipelines || {};

  // Provenance grade ordering (weakest -> strongest); the strongest grade among a
  // record's sources colours its summary source pill. Null when there are none.
  // Shared by projections (below) and drug bindings / NbN (further down), so the
  // "strongest grade wins" rule lives in one place.
  const GRADE_RANK = { llm: 1, sourced: 2, verified: 3 };
  const strongestGrade = (sources) => {
    let best = null;
    let rank = 0;
    for (const s of sources || []) {
      const r = GRADE_RANK[s.provenance] || 0;
      if (r > rank) {
        rank = r;
        best = s.provenance;
      }
    }
    return best;
  };

  // Build one "Found in" region entry (its per-region expression provenance +
  // the assay species). An expression source (e.g. a GtoPdb tissue-distribution
  // quote) carries the species it was checked in; the panel flags a non-human
  // claim amber, like the Ki chip, and shows the species in the pill tooltip.
  // Shared by receptor + non-receptor-target location lists so the species logic
  // lives once (both kinds carry the same location_sources node shape).
  // `uncertainty` is the region's own bullets (an animal-only claim, see
  // quotes/animal_evidence.py), kept raw like `sources`: they turn its pill orange.
  const locationEntry = (base, name, sources, uncertainty) => {
    const srcs = sources || [];
    const speciesList = srcs.map((s) => s.species).filter(Boolean);
    // Prefer a Human assay when any source carries one: a region we have confirmed
    // in human tissue is not a "non-human only" claim, so it must not keep the amber
    // tag just because another source (e.g. a rat GtoPdb quote) also backs it.
    const species = speciesList.includes("Human")
      ? "Human"
      : (speciesList[0] || "");
    return {
      base, name, sources: srcs,
      provenance: strongestGrade(srcs) || "llm",
      uncertainty: uncertainty || [],
      species,
      nonHuman: !!species && species !== "Human",
    };
  };

  // Normalize an owner's relative-expression density node (a receptor's or a
  // non-receptor target's; identical shape) for the panel. The emitted `profile` maps a
  // region base -> a z-score against that gene's own brain-wide average, so the numbers
  // are comparable WITHIN one owner and not across owners; `rel` therefore scales each
  // region against this owner's own strongest/weakest region, which is the only bar width
  // that means anything. A floor keeps the weakest region a visible sliver rather than
  // reading as "absent" (it is present: that is what the presence node said).
  /**
   * Normalize one enzyme's metabolizer-status profile (PharmFreq, corpus #13).
   *
   * Reshapes `{group: {phenotype: frequency}}` into the render order the emitted
   * vocabularies define, so the panel iterates data rather than a hardcoded list of
   * phenotype letters. Each group's row is the frequencies **in phenotype order**
   * (slowest clearance first), which is what makes the stacked bars comparable down
   * the column: the same colour sits at the same end of every bar.
   *
   * Returns null when the isoform has no published profile, which the panel shows as
   * a gap rather than inventing a flat "does not vary".
   */
  const variabilityEntry = (variability) => {
    if (!variability || !variability.profile) return null;
    const order = Object.keys(metaRecord.metabolizer_phenotypes || {});
    const groups = [];
    for (const key of Object.keys(metaRecord.metabolizer_groups || {})) {
      const row = variability.profile[key];
      if (!row) continue;
      groups.push({
        key,
        label: localize(metaRecord.metabolizer_groups[key]) || key,
        cells: order.filter((p) => row[p] != null).map((p) => {
          const def = metaRecord.metabolizer_phenotypes[p] || {};
          return {
            phenotype: p,
            freq: row[p],
            label: def.label ? localize(def.label) : p,
            note: def.note ? localize(def.note) : "",
          };
        }),
      });
    }
    if (!groups.length) return null;
    return {
      gene: variability.gene,
      groups,
      provenance: strongestGrade(variability.sources),
      sources: mapSources(variability.sources),
    };
  };

  const densityEntry = (density) => {
    if (!density || !density.profile) return null;
    const zs = Object.values(density.profile);
    if (zs.length < 2) return null;
    const min = Math.min(...zs);
    const max = Math.max(...zs);
    const span = max - min;
    const rel = {};
    for (const [base, z] of Object.entries(density.profile)) {
      rel[base] = span > 0 ? 0.08 + 0.92 * ((z - min) / span) : 1;
    }
    return {
      profile: density.profile,
      rel,
      reliability: density.reliability,
      donors: density.donors,
      provenance: density.grade || "llm",
      sources: density.sources || [],
    };
  };

  // Resolve each projection's colours from its kind (kept as the raw key, since it
  // indexes the colour/label maps): `color` is the per-transmitter colour (default
  // mode), `sign`/`signColor` the coarse excitatory/inhibitory view the colour
  // toggle switches to. Localize the display fields so the viewer reads plain
  // strings. `provenance` is the strongest grade among its `sources`, which colours
  // the summary source pill shown on a structure panel's connection row (the same
  // pill the binding rows use), so a pathway's source shows on both endpoints'
  // panels (null when it has no source).
  for (const p of projections) {
    p.color = projectionColors[p.kind] || "#ffffff";
    p.sign = kindSigns[p.kind] || "modulatory";
    p.signColor = signColors[p.sign] || "#ffffff";
    p.label = localize(p.label);
    p.description = localize(p.description);
    p.neurotransmitter = localize(p.neurotransmitter);
    p.provenance = strongestGrade(p.sources);
    // Reasons the quote does not actually state THIS pathway (the orange "uncertain"
    // badge a blanket sweep sentence earns, derived in quotes/uncertainty.py). Same
    // bullet shape a drug binding carries; always an array so the panel can test
    // `.length` without a guard. The bullets' sources stay raw, like `p.sources`, and
    // so do those of its per-claim split (`p.claims`, transmitter + sign): every
    // pathway source is read raw here, so normalizing one of them would be the odd
    // one out.
    p.uncertainty = p.uncertainty || [];
  }

  // Localize the structure + circuit display strings (the geometry/ids stay as
  // language-neutral keys).
  for (const s of structures) {
    s.name = localize(s.name);
    s.base_name = localize(s.base_name);
    // Hot-linked Wikipedia hero image for the structure panel (null when none was
    // fetched), mirroring a drug's molecule image. Not localized (raster art).
    s.structureImage = s.structure_image || null;
    // Further gif/svg from the structure's EN+FR articles, revealed by the panel's
    // "show more" (always an array, so the viewer can test .length).
    s.structureImageGallery = s.structure_image_gallery || [];
  }
  for (const c of circuits) {
    c.name = localize(c.name);
    // A circuit carries a baked description (offline fallback) plus an optional
    // Wikipedia link; its panel live-fetches the current lead like a structure. The
    // raw `wikipedia` field passes through untouched for appendReference to consume.
    c.description = c.description ? localize(c.description) : "";
    c.provenance = strongestGrade(c.sources);
    // Hot-linked Wikipedia illustration (hero + gallery), same shape as a structure's,
    // so the circuit panel reuses appendWikiImages.
    c.structureImage = c.structure_image || null;
    c.structureImageGallery = c.structure_image_gallery || [];
  }

  // Projection groups: the legend's per-pathway rows promoted to a sourced data
  // structure (one record per group, in both colour modes; see
  // generate_data.py PROJECTION_GROUPS). Localize the display strings and resolve
  // the source grade, exactly like a projection / circuit. The member pathways are
  // derived in the viewer (the projections whose kind/sign matches), so they are
  // not stored here. Indexed by `${mode}:${key}` so a legend row can find its
  // record by the grouping it stands for.
  const projectionGroupsByKey = new Map();
  for (const g of projectionGroups) {
    g.name = localize(g.name);
    g.description = g.description ? localize(g.description) : "";
    g.provenance = strongestGrade(g.sources);
    projectionGroupsByKey.set(`${g.mode}:${g.key}`, g);
  }

  // Fetch all shape files in parallel and attach them to their structure. Report
  // progress per file (these are the bulk of the load, especially on a slow link)
  // so the startup loading bar can advance.
  //
  // Deduplicated by url: a symmetric structure's two hemispheres share ONE shape
  // file (the right-side form, which `structure.mirror` flips for the left), so
  // 46 structures resolve to 26 files. Fetching per structure meant 20 redundant
  // requests, which on a phone is 20 extra round trips, and handed the mesher two
  // distinct-but-identical specs to build twice (see js/main.js `sdfItems`). The
  // parsed spec is then SHARED between the twins, which is safe because nothing
  // downstream mutates it: `buildGeometry` only reads, and the mesh budget's
  // `adjust` returns a copy.
  {
    let loaded = 0;
    const total = structures.length;
    onProgress?.({ stage: "shapes", loaded, total });
    const byUrl = new Map();
    await Promise.all(
      structures.map(async (s) => {
        let shape = byUrl.get(s.shape_file);
        if (!shape) {
          shape = fetchOrThrow(s.shape_file).then((r) => r.json());
          byUrl.set(s.shape_file, shape);
        }
        s.shape = await shape;
        onProgress?.({ stage: "shapes", loaded: (loaded += 1), total });
      }),
    );
  }

  const byId = new Map(structures.map((s) => [s.id, s]));

  // Resolve each receptor for the viewer. `locations` holds structure *base* ids
  // (like circuits, but one entry per region rather than per hemisphere); expand
  // each to the concrete structure ids actually emitted (both hemispheres, or the
  // bare id for a midline structure) so the marker layer can light them up, and
  // collect the side-stripped region names for the info panel. A `ubiquitous`
  // receptor (NMDA, GABA-A, ...) lights every structure. `focusable` is false for
  // the deliberate "stub" receptors (no CNS role, empty locations) so the legend
  // can render them as inert rows.
  const baseOf = (id) => id.replace(/_[RL]$/, "");
  const baseName = new Map();
  for (const s of structures) baseName.set(baseOf(s.id), s.base_name);
  const allIds = structures.map((s) => s.id);
  for (const r of receptors) {
    r.neurotransmitter = localize(r.neurotransmitter);
    r.description = r.description ? localize(r.description) : "";
    r.familyLabel = receptorFamilyLabels[r.family] || r.family;
    r.classLabel = receptorClassLabels[r.receptor_class] || r.receptor_class;
    r.signColor = signColors[r.sign] || "#ffffff";
    r.signLabel = signLabels[r.sign] || r.sign;
    r.synapticLabel = synapticLabels[r.synaptic] || r.synaptic;
    if (r.ubiquitous) {
      r.structureIds = allIds.slice();
    } else {
      r.structureIds = r.locations.flatMap((b) =>
        [b, `${b}_R`, `${b}_L`].filter((id) => byId.has(id)),
      );
    }
    r.locationNames = r.locations.map((b) => baseName.get(b) || b);
    // Per-region expression provenance: the "Found in" node "this receptor is
    // expressed in region B" is graded per region (default llm when unsourced), so
    // the panel shows a pill per row. Parallel to locations/locationNames.
    const locSrc = r.location_sources || {};
    const locDoubt = r.location_uncertainty || {};
    r.locationInfo = r.locations.map((b, i) =>
      locationEntry(b, r.locationNames[i], locSrc[b], locDoubt[b]));
    // How much of it sits in each region (one measured profile over those regions,
    // its own graded node). Null when unmeasured -> the panel just omits the bars.
    r.densityInfo = densityEntry(r.density);
    // A ubiquitous receptor is one "throughout the brain" expression node
    // (its location_sources under the "ALL" sentinel), graded like a region.
    if (r.ubiquitous) {
      r.ubiquitousInfo = {
        sources: locSrc.ALL || [],
        provenance: strongestGrade(locSrc.ALL) || "llm",
      };
    }
    r.focusable = r.ubiquitous || r.structureIds.length > 0;
  }

  // Resolve each drug for the viewer. A binding's `target` indexes the merged
  // drug_targets map; resolve its display name, the action label + net effect (and
  // the effect's swatch colour, driving the per-drug animation), and the concrete
  // structure ids it lights: a receptor-linked target reuses that receptor's
  // already-expanded structureIds, a ubiquitous one lights every structure, and a
  // non-receptor target expands its region bases to both hemispheres (like a
  // receptor's locations). The union over all bindings is the drug's affected set
  // (what the focus dims the brain down to). `keywords` feeds the search box.
  const receptorStructureIds = new Map(receptors.map((r) => [r.id, r.structureIds]));
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
  // Normalize a quote-level sources list (a binding's `sources` or a drug's
  // `nbn_sources`) into the shape the panel renders.
  const mapSources = (sources) =>
    (sources || []).map((s) => ({
      corpus: s.corpus,
      page: s.page != null ? s.page : null,
      quote: s.quote || "",
      provenance: s.provenance || "llm",
      // Where in the book the passage sits ({drug, section, subsection}, derived
      // by tools/fetch/fetch_quote_headers.py). Absent for a corpus with no page
      // structure (a Ki CSV row) and for a quote whose heading could not be
      // resolved: the tooltip then simply shows no breadcrumb.
      heading: s.heading || null,
      // How this quote came to be cited (see meta.quotePipelines): the tooltip ends
      // with the chain, so a reader can tell a parser copying a table cell from a
      // model reading a book page.
      pipeline: s.pipeline || null,
      // The page's download date (editable online corpora only, see withFetched).
      fetched: s.fetched || null,
      // The reuse licence of an open-access text quoted from (a Europe PMC full-text
      // paper, e.g. "CC BY-NC"), credited in the tooltip; null for every other source.
      licence: s.licence || null,
      // A PDSP CSV row cited in place of a quote (a measured Ki, or an inactive
      // ceiling a curated denial rests on): the tooltip spells the row out.
      kiRow: s.ki_id != null ? {
        id: s.ki_id, valueNm: s.value_nm, note: s.note || "", species: s.species || "",
        radioligand: s.radioligand || "", reference: s.reference || "",
      } : null,
    }));
  // The per-claim split (tools/data_generators/quotes/attestation.py): a node that
  // asserts several things at once carries one graded entry per part, so the part a
  // quote does not name reads `llm` instead of borrowing the node's grade. Normalized
  // like any other source list, since each entry's pill opens the same tooltip.
  const mapClaims = (claims) => {
    if (!claims) return null;
    const out = {};
    for (const [name, entry] of Object.entries(claims)) {
      out[name] = {
        grade: entry.grade || "llm",
        sources: mapSources(entry.sources),
        // A sub-claim can carry its own "uncertain" bullets (a denial, a set-level
        // sentence), independent of its owner's.
        uncertainty: mapUncertainty(entry.uncertainty),
      };
    }
    return out;
  };
  // Reasons the quote does not settle the claim (the orange "uncertain" badge; derived
  // or curated in tools/data_generators/quotes/). Each bullet is a reason `kind` + slot
  // `args` + its own source, or `absence` when the point IS that the corpus never says
  // it; the sentence itself is an i18n string, so nothing here is stored prose. Always
  // an array, so a panel can test `.length` with no guard.
  const mapUncertainty = (list) =>
    (list || []).map((u) => ({
      kind: u.kind,
      args: u.args || {},
      absence: !!u.absence,
      sources: mapSources(u.sources),
    }));
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
  // A brand name can carry a parenthetical note from the source's own list, and two
  // very different things hide in there. A FORMULATION note ("Saphris (sublingual)")
  // is the same molecule delivered another way. A COMPOSITION note ("Suboxone (with
  // naloxone)") is a DIFFERENT product, so letting it headline the drug misnames it:
  // buprenorphine is not Suboxone. See the primaryBrand pick below.
  const BRAND_NOTE = /\s*\([^()]*\)\s*$/;
  const BRAND_COMBO = /\((?:with|in combination|\+)/i;
  // A prodrug (node kind drug_prodrug) is inactive itself and carries no binding of
  // its own (bar the activating enzyme it is the substrate of, levodopa at AADC, kept
  // first), yet focusing it should light what its active metabolite hits. So before
  // the loop resolves bindings, it borrows each metabolite's raw bindings (its own
  // `bindings[]`, else its linked modeled drug's), tagged `via_metabolite`: the scene,
  // flow and "Direct molecular targets" treat them like the drug's, while every list that counts a
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
  for (const d of drugs) {
    if (!d.prodrug) continue;
    d.bindings = (d.bindings || []).concat((d.metabolites || []).flatMap((m) => {
      const linked = m.drug_id ? rawDrugById.get(m.drug_id) : null;
      const own = (m.bindings || []).length ? m.bindings : linked ? linked.bindings || [] : [];
      return own.map((b) => ({ ...b, via_metabolite: m.name }));
    }));
  }
  for (const d of drugs) {
    d.description = d.description ? localize(d.description) : "";
    // Provenance grade of the description (llm synthesis vs a sourced Wikipedia
    // lead); the panel shows a pill beside it.
    d.descriptionProvenance = d.description_provenance || null;
    d.nbn = d.nbn ? localize(d.nbn) : "";
    // The NbN is quote-sourced like a binding (verbatim Stahl line); the panel
    // shows a provenance pill next to it. Null grade when unsourced.
    d.nbnSources = mapSources(d.nbn_sources);
    d.nbnProvenance = strongestGrade(d.nbn_sources);
    // True when the "nomenclature" is Stahl's drug-class descriptor, not a formal
    // Neuroscience-based Nomenclature (a newer drug Stahl gives no NbN); the panel
    // flags it so the value isn't misread as an official NbN code.
    d.nbnNonstandard = !!d.nbn_nonstandard;
    d.categoryLabels = (d.categories || []).map((c) => drugCategoryLabels[c] || c);
    d.category = d.categoryLabels[0] || "";
    // The drug's class classification ("this drug is an SSRI/...") is its own graded
    // node: the panel shows a provenance pill on the Class row. Default "llm" (LLM-
    // authored); `category_sources` (quote-level, if any) upgrade the emitted grade.
    d.categorySources = mapSources(d.category_sources);
    d.categoryProvenance = d.category_provenance || "llm";
    // Vendored molecular-structure SVG path (data/molecules/<id>.svg), set by the
    // generator only when the file was fetched; the drug panel embeds it as an
    // <img>. Null when no SVG is available (no image shown).
    d.structureImage = d.structure_image || null;
    // Elimination half-life (T½): {hours, hours_max?} passed through raw; the panel
    // formats it via formatHalfLife (js/main.js). Its own sourced node, so carry the
    // strongest grade + sources for the pill next to it.
    d.halfLife = d.half_life || null;
    d.halfLifeSources = mapSources(d.half_life_sources);
    d.halfLifeProvenance = strongestGrade(d.half_life_sources);
    // Time to peak plasma concentration (Tmax), same shape and same treatment: its
    // own sourced node, and the other end of the curve js/sim-model.js draws (the T½
    // sets the fall, this sets the rise). Null on the ~70% of drugs no corpus states
    // a peak for; the simulation then uses its single assumed peak.
    d.tmax = d.tmax || null;
    d.tmaxSources = mapSources(d.tmax_sources);
    d.tmaxProvenance = strongestGrade(d.tmax_sources);
    // Formulations: one per release type a source names, each its own graded node
    // (the release) holding the brands / Tmax / T½ measured or sold for THAT product.
    // Molecule-level `brands` / `tmax` / `halfLife` above are what no source ties to
    // one product. See docs/DRUGS.md "Formulations".
    d.formulations = (d.formulations || []).map((f) => ({
      release: f.release,
      label: releaseLabels[f.release] || f.release,
      releaseSources: mapSources(f.release_sources),
      releaseProvenance: strongestGrade(f.release_sources),
      brands: (f.brands || []).map((b) => ({ ...b, release: f.release })),
      tmax: f.tmax || null,
      tmaxSources: mapSources(f.tmax_sources),
      tmaxProvenance: strongestGrade(f.tmax_sources),
      halfLife: f.half_life || null,
      halfLifeSources: mapSources(f.half_life_sources),
      halfLifeProvenance: strongestGrade(f.half_life_sources),
    }));
    // Regulatory history: the earliest approval the source states (one node) and
    // each market withdrawal (one node each; none at all when never withdrawn).
    // Labels resolved here so the panel and the node browser share one wording.
    const fa = d.first_approval;
    d.firstApproval = fa ? {
      year: fa.year,
      countryLabel: fa.country ? historyCountries[fa.country] || fa.country : null,
      agencyLabel: fa.agency ? historyAgencies[fa.agency] || fa.agency : null,
      // The earliest approval in that one country (a regulator's own register).
      national: !!fa.national,
      sources: mapSources(d.first_approval_sources),
      provenance: strongestGrade(d.first_approval_sources),
    } : null;
    // Who the drug comes from (kinds drug_originator / drug_originator_country /
    // drug_holders): the originator lab (its `now` name cited apart, shown in its
    // tooltip, graded by the name's own sources), that lab's country, and the current
    // marketing-authorisation holders, one node per market.
    const og = d.originator;
    d.originator = og ? {
      name: og.name,
      now: og.now || null,
      sources: mapSources([...(d.originator_sources || []), ...(d.originator_now_sources || [])]),
      provenance: strongestGrade(d.originator_sources),
      country: d.originator_country ? {
        label: historyCountries[d.originator_country] || d.originator_country,
        sources: mapSources(d.originator_country_sources),
        provenance: strongestGrade(d.originator_country_sources),
      } : null,
    } : null;
    d.holders = (d.holders || []).map((h) => ({
      market: h.market,
      marketLabel: historyCountries[h.market] || h.market,
      names: h.names,
      sources: mapSources(h.sources),
      provenance: strongestGrade(h.sources),
      uncertainty: mapUncertainty(h.uncertainty),   // e.g. a curated `contradicted`
    }));
    // Prodrug flag (kind drug_prodrug): its own graded claim; the borrowed
    // bindings are wired by the prodrug pass above this loop.
    d.prodrug = d.prodrug ? {
      sources: mapSources(d.prodrug_sources),
      provenance: strongestGrade(d.prodrug_sources),
    } : null;
    // A salt's declared composition (kind drug_constituents): its own graded claim,
    // pilled on the combo box; the borrowed bindings are wired above this loop.
    d.constituentsClaim = (d.constituents || []).length ? {
      sources: mapSources(d.constituents_sources),
      provenance: strongestGrade(d.constituents_sources),
    } : null;
    // Therapeutic drug monitoring (kinds drug_therapeutic_range / drug_alert_level,
    // AGNP corpus #19): each its own graded node, both from one Table 5 row.
    const trr = d.therapeutic_range;
    d.therapeuticRange = trr ? {
      low: trr.low, high: trr.high, unit: trr.unit, analyte: trr.analyte || null,
      tdmLevel: trr.tdm_level || null,
      sources: mapSources(d.therapeutic_range_sources),
      provenance: strongestGrade(d.therapeutic_range_sources),
    } : null;
    const al = d.alert_level;
    d.alertLevel = al ? {
      value: al.value, unit: al.unit, analyte: al.analyte || null,
      sources: mapSources(d.alert_level_sources),
      provenance: strongestGrade(d.alert_level_sources),
    } : null;
    // Physicochemistry and brain entry (kinds drug_lipophilicity / drug_polar_surface /
    // drug_bbb, PubChem #21 + B3DB #22), one graded node each, rendered by
    // js/physchem.js. `xlogp` / `tpsa` arrive as bare numbers, so they are wrapped.
    const physNode = (srcs, rest) => ({
      ...rest, sources: mapSources(srcs), provenance: strongestGrade(srcs) });
    d.xlogp = d.xlogp != null ? physNode(d.xlogp_sources, { value: d.xlogp }) : null;
    d.tpsa = d.tpsa != null ? physNode(d.tpsa_sources, { value: d.tpsa }) : null;
    d.bbb = d.bbb ? physNode(d.bbb_sources, {
      label: d.bbb.label, logbb: d.bbb.logbb ?? null, logbbMax: d.bbb.logbb_max ?? null,
    }) : null;
    // Pre-prescription workup (kind drug_workup, BETA): one node per (test, timing) the
    // French label (RCP 4.2 / 4.3 / 4.4) asks for, rendered by js/workup.js + main.js.
    d.workup = (d.workup || []).map((w) => ({
      test: w.test, timing: w.timing,
      testLabel: workupTests[w.test] || w.test,
      timingLabel: workupTimings[w.timing] || w.timing,
      conditions: w.conditions || [],   // verbatim French spans: a conditional ask
      sources: mapSources(w.sources),
      provenance: strongestGrade(w.sources),
      uncertainty: mapUncertainty(w.uncertainty),   // e.g. a curated `contradicted`
    }));
    d.withdrawals = (d.withdrawals || []).map((w) => ({
      year: w.year,
      country: w.country,
      countryLabel: historyCountries[w.country] || w.country,
      // A market scope ("worldwide", "most markets") rather than one country: the
      // panel lists it first in a grouped row (js/drug-history.js groupWithdrawals).
      scope: historyScopes.has(w.country),
      reason: w.reason,
      reasonLabel: withdrawalReasons[w.reason] || w.reason,
      sources: mapSources(w.sources),
      provenance: strongestGrade(w.sources),
    }));
    // Metabolism: which enzymes handle this drug, or are inhibited/induced by it.
    // Pharmacokinetics, so unlike a binding it lights nothing in the 3D scene; it
    // feeds the panel's Metabolism list, the Enzymes browse section, and the derived
    // drug -> drug interaction edges below. Labels come from meta.enzymes* so no
    // isoform name is hardcoded here.
    d.enzymes = (d.enzymes || []).map((e) => {
      const def = enzymeDefs[e.enzyme] || {};
      const role = enzymeRoles[e.role] || {};
      return {
        ...e,
        label: def.label || e.enzyme,
        wikipedia: def.wikipedia || null,
        roleLabel: role.label ? localize(role.label) : e.role,
        // The drug panel's group heading over this role's rows ("Substrate of").
        roleHeading: role.heading ? localize(role.heading) : (role.label ? localize(role.label) : e.role),
        // What the drug does to that enzyme's throughput: +1 inhibits (a substrate
        // co-prescribed with it accumulates), -1 induces (it is cleared faster), 0
        // for a substrate, which sets no tone of its own.
        direction: role.direction || 0,
        strengthLabel: enzymeStrengths[e.strength]
          ? localize(enzymeStrengths[e.strength]) : null,
          sources: mapSources(e.sources),
        provenance: strongestGrade(e.sources),
        // Another corpus denies this row (quotes/contradictions.py): the pill goes
        // orange and its tooltip leads with the denial, then shows this row's own
        // quote. Empty for all but the handful of contradicted rows.
        uncertainty: mapUncertainty(e.uncertainty),
        // How much of the clearing this isoform does is its own graded claim.
        claims: mapClaims(e.claims),
      };
    });
    // CPIC's prescribing guidance for this drug (corpus #15), one node per (gene,
    // phenotype) row. The one place this dataset carries a clinical action, and the
    // only one that needs a *second* dataset to be read at all: each row is paired
    // here with how common that phenotype is per population group (corpus #13, on the
    // enzyme), because "poor metabolizer" means nothing to a reader until they know
    // whether that is 1 patient in 20 or 1 in 1000. A gene with no profile cannot
    // reach this point (generate_data refuses it), so `groups` is always populated.
    d.pgx = (d.pgx || []).map((block) => {
      const variability = variabilityEntry((enzymeDefs[block.enzyme] || {}).variability);
      const freqs = new Map((variability ? variability.groups : [])
        .map((g) => [g.key, new Map(g.cells.map((c) => [c.phenotype, c]))]));
      return {
        ...block,
        label: (enzymeDefs[block.enzyme] || {}).label || block.gene,
        population: block.population ? localize(block.population) : null,
        // The population groups the frequency table offers, so the picker lists what
        // can actually be answered rather than a fixed continent list.
        groups: (variability ? variability.groups : []).map((g) => ({
          key: g.key, label: g.label,
        })),
        rows: (block.rows || []).map((row) => {
          const def = (metaRecord.metabolizer_phenotypes || {})[row.phenotype] || {};
          return {
            ...row,
            label: def.label ? localize(def.label) : row.phenotype,
            note: def.note ? localize(def.note) : "",
            // group key -> {freq, label}: what the panel reads once the user picks a
            // group. A phenotype the gene has no row for is absent here rather than
            // zero, because nobody measured it at 0%.
            freqByGroup: new Map([...freqs].map(([key, cells]) =>
              [key, cells.get(row.phenotype) || null])),
            sources: mapSources(row.sources),
            provenance: strongestGrade(row.sources),
          };
        }),
      };
    });
    // Derived, never stored (like pkInteractionsOf below): the isoforms this drug
    // is BOTH a substrate of and a modulator of, so it changes its own clearance
    // (autoinhibition, or autoinduction for an inducer) and its dose/level relation
    // is not a straight line. No single enzyme row above can say this: each states
    // one role, and it is their coincidence on one isoform that is the claim. An
    // inference off graded rows, so the panel words it conditionally and shows no
    // pill of its own (the rows it reads carry theirs).
    d.autoModulation = d.enzymes.filter((e) => e.direction !== 0
      && d.enzymes.some((o) => o.enzyme === e.enzyme && o.role === "substrate"));
    const affected = new Set();
    d.bindings = (d.bindings || []).map((b) => {
      // Display + provenance fields come from the shared resolver; the drug loop
      // then layers on the animation-only fields (structureIds/flow/weights). See
      // bindingDisplayFields. `tgt` is reused, `disp.tgt` is not returned to callers.
      const disp = bindingDisplayFields(b);
      const { tgt, affinityOnly, peripheral, effect } = disp;
      // Neither an affinity-only nor a peripheral binding touches the scene: the
      // first states no direction, the second states one that happens elsewhere.
      const inert = affinityOnly || peripheral;
      // An affinity_only binding has a measured Ki but no known direction (neither
      // PDSP nor GtoPdb states one): it is listed in the panel with its Ki but has no
      // action/effect, so it never animates and contributes nothing to the lit-region
      // union or the flow. Every binding that DOES state a direction animates,
      // whichever corpus sourced it.
      let structureIds = [];
      if (inert) {
        structureIds = [];
      } else if (tgt.ubiquitous) {
        structureIds = allIds.slice();
      } else if (tgt.receptor && receptorStructureIds.has(tgt.receptor)) {
        structureIds = receptorStructureIds.get(tgt.receptor).slice();
      } else {
        structureIds = (tgt.regions || []).flatMap((bse) =>
          [bse, `${bse}_R`, `${bse}_L`].filter((id) => byId.has(id)),
        );
      }
      if (!inert) for (const id of structureIds) affected.add(id);
      return {
        target: disp.target,
        targetName: disp.targetName,
        system: disp.system,
        // The projection kind this binding's target system feeds (meta.system_flow_
        // kinds), null when the system has no modeled ascending pathway or the
        // binding is affinity-only. Lets a panel list the "neurotransmitter tone" per
        // binding and lets d.flowKinds below dedupe from a single field.
        flowKind: inert ? null : systemFlowKinds[tgt.system] || null,
        receptor: disp.receptor,
        affinityOnly,
        peripheral,
        action: disp.action,
        actionLabel: disp.actionLabel,
        effect,
        effectColor: disp.effectColor,
        effectLabel: disp.effectLabel,
        note: disp.note,
        tentative: disp.tentative,
        structureIds,
        // Relative engagement from the measured Ki (0.35..1), NOT effect size.
        // Scales the dot cloud in drug-anim; also weights this binding's system
        // tone below. Neutral mid-value when no Ki.
        affinityWeight: inert ? 0 : affinityWeightOf(b.ki),
        // Signed tone-setter contribution to its system's ascending flow (+1 raises
        // the transmitter's tone, -1 lowers, 0 = not a tone-setter -> dots only).
        toneSign: inert ? 0 : toneSignOf(tgt, b.action),
        // Why it sets that tone (meta.tone_rules driver, e.g. "reuptake_block"), shown
        // in the drug panel's tone breakdown; null when it sets none.
        toneRule: inert ? null : toneRuleOf(tgt, b.action),
        // Its share of that tone: the bucket factor (an autoreceptor counts half a
        // reuptake block) times the floor-free Ki weight (see toneBySystem).
        toneFactor: inert ? 1 : toneFactorOf(tgt),
        toneWeight: inert ? 0 : toneWeightOf(b.ki),
        // Per-claim sources ({corpus, page, quote, provenance}); `provenance` is the
        // strongest grade among the quote sources AND the measured Ki. See
        // bindingDisplayFields / _binding_grade in generate_data.py.
        sources: disp.sources,
        provenance: disp.provenance,
        // The direction's own grade (node kind `drug_binding_action`), from the quote
        // sources alone. null = affinity_only, i.e. no direction claim to grade.
        actionProvenance: disp.actionProvenance,
        unknown: disp.unknown,
        // Non-empty -> the badge reads "uncertain" instead of the green check.
        uncertainty: disp.uncertainty,
        // The measured PDSP Ki (own verified badge), null when absent.
        ki: disp.ki,
        // Borrowed by a prodrug from this active metabolite (see the prodrug pass
        // above the loop); null on the drug's own bindings.
        viaMetabolite: b.via_metabolite || null,
      };
    });
    d.structureIds = [...affected];
    // By-mechanism flow, split from the dots (approach 3): a projection kind gets a
    // flow overlay ONLY from *tone-setter* bindings (transporters, enzymes, vesicle
    // proteins, presynaptic inhibitory autoreceptors), never from a postsynaptic
    // receptor (those stay dots). Per engaged kind we sum toneSign*toneFactor*toneWeight so
    // combos and opposing autoreceptors resolve to a net signed tone; the sign is the
    // flow direction (boost vs damp) and the clamped magnitude its intensity.
    d.flowSystems = toneBySystem(d.bindings);
    // Normalize to a per-drug *relative* intensity (`rel`, 0..1): the drug's strongest
    // engaged system streams at 1, the rest in proportion. Dosage is highly variable,
    // so what the flow overlay should show is the relative "dirtiness" across systems,
    // not an absolute magnitude. `weight` (absolute affinity) is kept for the panel's
    // strongest-binding pill; `rel` drives the animation's density/speed.
    const maxFlowWeight = Math.max(0, ...Object.values(d.flowSystems).map((f) => f.weight));
    for (const f of Object.values(d.flowSystems)) {
      f.rel = maxFlowWeight ? f.weight / maxFlowWeight : 1;
    }
    // Drives the flowing-beads overlay (main.js filters arrows by these kinds, then
    // js/circuit-anim.js animates them with the per-kind direction/weight above) and
    // the panel's "Neurotransmitter tone" list. Empty for a drug that sets no tone (a
    // purely postsynaptic agent gets just dots + wash).
    d.flowKinds = Object.keys(d.flowSystems);
    // Static "context" pathways (viewer-side, split from the flow): the ascending
    // systems the drug acts *within* through a POSTSYNAPTIC receptor (a flow-mapped
    // system carrying no tone-setter binding) e.g. an H1 / 5-HT2 / postsynaptic-D2
    // blocker. Blocking a postsynaptic receptor does NOT change the transmitter's
    // release/tone, so these earn no beads and no direction: main.js pins them at a
    // dimmed *static* opacity so a purely postsynaptic agent (an antihistamine) still
    // visibly engages its system's pathways, without falsely claiming a tone shift. A
    // kind already flowing (in flowSystems) is excluded, the beads already cover it.
    const ctxKinds = new Set();
    for (const b of d.bindings) {
      if (b.flowKind && !b.toneSign && !d.flowSystems[b.flowKind]) ctxKinds.add(b.flowKind);
    }
    d.contextKinds = [...ctxKinds];
    // Every drug is focusable, bindings or not: its panel (brands, kinetics,
    // metabolism, addons) is worth opening even when there is nothing to light in 3D
    // (lithium), so search + the drug list reach it like any other.
    d.focusable = d.focusable !== false;
    // Commercial brand names, ordered for THIS locale (the `region` tag orders only,
    // it is never shown): a French reader sees fr -> eu -> na, everyone else
    // na -> eu -> fr; within a region the authored order is kept (first = most iconic).
    // `brandsOrdered` are the graded brand nodes in that order (deduped by name so a
    // name shared across regions shows once, keeping its first/top-region source);
    // `primaryBrand` is the single most-iconic name shown after the drug name
    // everywhere (see drugDisplayName), `brandNames` the full list, `displayName` the
    // name + primary. All brand names also feed search. See docs/DRUGS.md "Drugs".
    const brandRank = window.__I18N__.lang === "fr"
      ? { fr: 0, eu: 1, na: 2 }
      : { na: 0, eu: 1, fr: 2 };
    const brandSeen = new Set();
    // Formulation brands join after the molecule's own (tagged with their `release`),
    // so search and the primary brand see every name while the panel's Brands row can
    // keep to the molecule's.
    d.brandsOrdered = [...(d.brands || []), ...d.formulations.flatMap((f) => f.brands)]
      // `region` is one tag, or a list when one name is sold in several regions.
      .map((b, i) => ({ b, r: Math.min(...[].concat(b.region).map((g) => brandRank[g] ?? 9)), i }))
      .sort((x, y) => x.r - y.r || x.i - y.i)
      .map((x) => x.b)
      .filter((b) => {
        const k = (b.name || "").toLowerCase();
        if (!k || brandSeen.has(k)) return false;
        brandSeen.add(k);
        return true;
      });
    d.brandNames = d.brandsOrdered.map((b) => b.name);
    // Locale-ordered brand *stems*, the note dropped: a brand listed both plainly and
    // with a note (naltrexone's "Revia (oral)" in the NA list, "Revia" in the FR one)
    // is ONE brand, and counts as plainly named wherever it first appeared.
    const stems = [];
    const stemAt = new Map();
    for (const n of d.brandNames) {
      const stem = n.replace(BRAND_NOTE, "");
      const k = stem.toLowerCase();
      let e = stemAt.get(k);
      if (!e) { e = { stem, plain: false, combo: false }; stemAt.set(k, e); stems.push(e); }
      if (!BRAND_NOTE.test(n)) e.plain = true;
      else if (BRAND_COMBO.test(n)) e.combo = true;
    }
    // The headline brand is the first plainly-named one, else the first whose only
    // note is a formulation, so a combination product never quietly stands in for the
    // single molecule: Stahl lists nothing but the naloxone combos and the depots for
    // buprenorphine, whose plain brand (Subutex here, Temgésic in French) is the one
    // to show. A drug that IS a combination keeps its own, since it is already named.
    const selfCombo = /[+/]/.test(d.name || "");
    d.primaryBrand = (stems.find((e) => e.plain)
      || stems.find((e) => selfCombo || !e.combo)
      || {}).stem || d.brandNames[0] || null;
    // `label` = the name plus its display-only chemical synonym when the generator
    // emits one (DRUG_NAME_QUALIFIERS: "Paliperidone (9-OH-risperidone)"); `name`
    // itself stays the INN, which the external lookup links search by.
    d.label = d.name_qualifier ? `${d.name} (${d.name_qualifier})` : d.name;
    d.displayName = d.primaryBrand ? `${d.label} (${d.primaryBrand})` : d.label;
    // `aliases` are the search-only alternate names (GHB for sodium oxybate, ecstasy
    // for MDMA, ...). They join the haystack and are never rendered: a drug is always
    // shown under its own name, so an alias only ever helps someone find it.
    d.keywords = [...d.categoryLabels, d.nbn, ...d.brandNames, ...(d.aliases || []),
                  d.name_qualifier,
                  ...d.bindings.map((b) => b.targetName)]
      .filter(Boolean)
      .join(" ");
  }

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

  const { drugsByTarget, prodrugsByTarget } = indexDrugsByTarget(drugs);

  // The Enzymes browse list + its reverse index, the metabolism mirror of `targets` /
  // `drugsByTarget` above. One entry per isoform any drug actually touches (an isoform
  // in meta.enzymes that nothing references would be an empty panel), each carrying
  // the drugs split by role so the panel can head them "Substrates / Inhibitors /
  // Inducers" without re-scanning the corpus.
  const drugsByEnzyme = new Map();
  // The same index for the OTHER metabolism relation: which active metabolites this
  // isoform forms. Kept apart from the role rows because it is a different claim (the
  // enzyme is the maker, not the handler) and the enzyme panel heads it separately.
  const metabolitesByEnzyme = new Map();
  for (const d of drugs) {
    for (const e of d.enzymes) {
      if (!drugsByEnzyme.has(e.enzyme)) drugsByEnzyme.set(e.enzyme, []);
      drugsByEnzyme.get(e.enzyme).push({ drug: d, enzyme: e });
    }
    for (const m of d.metabolites) {
      for (const f of m.formedBy || []) {
        if (!metabolitesByEnzyme.has(f.enzyme)) metabolitesByEnzyme.set(f.enzyme, []);
        metabolitesByEnzyme.get(f.enzyme).push({ drug: d, metabolite: m, formedBy: f });
      }
    }
  }
  const enzymes = [...new Set([...drugsByEnzyme.keys(), ...metabolitesByEnzyme.keys()])]
    .map((id) => ({
      id,
      label: (enzymeDefs[id] || {}).label || id,
      wikipedia: (enzymeDefs[id] || {}).wikipedia || null,
      rows: drugsByEnzyme.get(id) || [],
      metabolites: metabolitesByEnzyme.get(id) || [],
      // How fast people clear a drug through this isoform, per population group
      // (PharmFreq, corpus #13). One graded node for the whole profile, like an
      // expression density profile; absent for an isoform the source does not cover,
      // which the panel renders as a gap rather than as "does not vary".
      variability: variabilityEntry((enzymeDefs[id] || {}).variability),
      keywords: [id, (enzymeDefs[id] || {}).label || id].join(" ").toLowerCase(),
    }))
    .sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }));

  /**
   * The pharmacokinetic interactions implied by the enzyme nodes, for one drug.
   *
   * Derived, never authored, exactly like `flowSystems` and circuit membership: an
   * inhibitor (or inducer) of an enzyme meets every substrate of that same enzyme.
   * Recomputing it here means it can never drift from the nodes it comes from.
   *
   * `direction` is what happens to the OTHER drug's blood level: +1 when this drug
   * inhibits an enzyme the other is a substrate of (the other accumulates), -1 when
   * it induces one (the other is cleared faster). A drug that is only a substrate
   * has no effect of its own, but is still *affected* by others, so both sides are
   * returned. This is a flag to check, never a contraindication: the panel says so.
   * @param {object} drug
   * @returns {{affects: object[], affectedBy: object[]}}
   */
  function pkInteractionsOf(drug) {
    // Keyed by (other drug, direction), not by enzyme: two drugs often meet at more
    // than one isoform (fluoxetine inhibits both CYP2D6 and CYP3A4, aripiprazole is
    // a substrate of both), and listing that pair twice reads as a rendering bug.
    // One row per pair, naming every enzyme they share.
    const merge = (map, other, enzymeRow, direction) => {
      if (other.id === drug.id) return;
      const key = `${other.id}:${direction}`;
      const hit = map.get(key);
      if (hit) {
        if (!hit.enzymes.some((x) => x.enzyme === enzymeRow.enzyme)) {
          hit.enzymes.push(enzymeRow);
        }
        return;
      }
      map.set(key, { drug: other, enzymes: [enzymeRow], direction, key });
    };
    const affects = new Map();
    const affectedBy = new Map();
    for (const e of drug.enzymes) {
      const rows = drugsByEnzyme.get(e.enzyme) || [];
      if (e.direction !== 0) {
        // This drug modulates the enzyme: it moves every substrate of it.
        for (const r of rows) {
          if (r.enzyme.role === "substrate") merge(affects, r.drug, e, e.direction);
        }
      }
      if (e.role === "substrate") {
        // This drug rides the enzyme: every modulator of it moves this drug.
        for (const r of rows) {
          if (r.enzyme.direction !== 0) {
            merge(affectedBy, r.drug, r.enzyme, r.enzyme.direction);
          }
        }
      }
    }
    return { affects: [...affects.values()], affectedBy: [...affectedBy.values()] };
  }

  // Build the merged "Receptors & targets" browse list: one normalized entry per
  // focusable *thing a drug can act on*, so a transporter (SERT), enzyme (MAO-A) or
  // channel (Nav) can be explored on its own, not only as a line in a drug's "Acts
  // on" list. Two sources, one shape: every modeled receptor (kind "receptor",
  // keeping its sign swatch + full classification for the panel), then every
  // *non-receptor* drug_targets entry (the receptor-linked ones are already covered
  // by the receptors above). Both carry `system` (the neurotransmitter family the
  // legend groups by; null -> the "Other" heading), a swatch colour, the expanded
  // `structureIds` to light, a `focusable` flag (false when there is no modeled
  // region, like a receptor stub) and search `keywords`. A receptor entry points
  // back at its record (panel reuses showReceptor); a non-receptor one carries the
  // display fields showTarget needs.
  const targets = [];
  for (const r of receptors) {
    targets.push({
      id: r.id,
      kind: "receptor",
      name: r.name,
      system: r.family,
      swatchColor: r.signColor,
      structureIds: r.structureIds,
      ubiquitous: !!r.ubiquitous,
      focusable: r.focusable,
      receptor: r,
      keywords: [r.familyLabel, r.classLabel, r.signLabel, r.neurotransmitter]
        .filter(Boolean).join(" "),
    });
  }
  for (const [id, tgt] of Object.entries(drugTargets)) {
    if (tgt.receptor) continue; // already listed as a receptor above
    const structureIds = (tgt.regions || []).flatMap((b) =>
      [b, `${b}_R`, `${b}_L`].filter((sid) => byId.has(sid)),
    );
    const typeLabel = targetTypeLabels[tgt.type] || tgt.type || "";
    const systemLabel = tgt.system ? receptorFamilyLabels[tgt.system] || tgt.system : "";
    targets.push({
      id,
      kind: tgt.type || "target",
      name: localize(tgt.name),
      system: tgt.system || null,
      swatchColor: targetTypeColors[tgt.type] || "#9aa0a6",
      structureIds,
      ubiquitous: false,
      focusable: structureIds.length > 0,
      receptor: null,
      typeLabel,
      systemLabel,
      wikipedia: tgt.wikipedia || "",
      // Representative HGNC symbol (SERT -> SLC6A4), an identifier, not a graded
      // claim: what the gene-keyed ClinPGx lookup link searches for.
      gene: tgt.gene || "",
      // A receptor_group's modeled subtype receptor ids (α2 -> α2A/B/C/D), a
      // sourceless taxonomy (meta.drug_targets[].subtypes). The panel lists each
      // subtype's own interacting drugs in a dropdown; empty for a non-group target.
      subtypes: tgt.subtypes || [],
      // Source grade backing this target's classification (type / system / regions),
      // shown as the panel's "Source" pill (default "llm"); `sources` carries the
      // quote-level source(s) so the pill tooltip can show the verbatim quote.
      classificationProvenance: tgt.classification_provenance || "llm",
      sources: tgt.sources || [],
      // Tone-polarity sub-claim ("engaging this target raises/lowers system tone"):
      // its OWN graded node (kind target_polarity), distinct from the classification
      // grade, because the vesicular/sign/synaptic flags flip the flow-overlay sign.
      // Present only for a target that carries a polarity flag; the panel renders a
      // dedicated pilled row so a wrong direction is not hidden behind the type pill.
      vesicular: !!tgt.vesicular,
      polaritySign: tgt.sign || null,
      polaritySynaptic: tgt.synaptic || null,
      polarityProvenance: tgt.polarity_provenance || null,
      polaritySources: tgt.polarity_sources || [],
      locationNames: (tgt.regions || []).map((b) => baseName.get(b) || b),
      // The raw base ids parallel to locationNames, so the panel can make each
      // "Found in" row jump to that structure (the receptor records keep their own
      // `locations` for the same purpose).
      locationBases: (tgt.regions || []).slice(),
      // Per-region expression provenance ("Found in"), parallel to locationBases:
      // "target T is found in region B" is its own graded node (default llm when
      // unsourced), so the panel shows a per-row pill, exactly like a receptor's
      // locationInfo. From the emitted target.location_sources ({base: [source]}).
      locationInfo: (tgt.regions || []).map((b) =>
        locationEntry(b, baseName.get(b) || b, (tgt.location_sources || {})[b],
          (tgt.location_uncertainty || {})[b])),
      // Relative amount per region, the mirror of a receptor's densityInfo.
      densityInfo: densityEntry(tgt.density),
      keywords: [typeLabel, systemLabel].filter(Boolean).join(" "),
    });
  }

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

  // The reverse of a receptor's "Found in": region base -> the targets expressed
  // there. Same node, read from the other end (the expression claim belongs to the
  // (target, region) pair, not to the target), so each entry carries THAT region's
  // own graded `info` and the structure panel shows the very pill the receptor panel
  // shows. A ubiquitous receptor is listed in every region under its single
  // "throughout the brain" node, which is the one expression claim it has.
  const targetsByStructure = new Map();
  const pushTarget = (base, entry) => {
    if (!baseName.has(base)) return; // an expression claim on an unmodeled region
    if (!targetsByStructure.has(base)) targetsByStructure.set(base, []);
    targetsByStructure.get(base).push(entry);
  };
  for (const tgt of targets) {
    const rec = tgt.receptor;
    if (rec && rec.ubiquitous) {
      for (const base of baseName.keys()) {
        pushTarget(base, { target: tgt, info: rec.ubiquitousInfo, ubiquitous: true });
      }
      continue;
    }
    const bases = rec ? rec.locations : tgt.locationBases;
    const infos = rec ? rec.locationInfo : tgt.locationInfo;
    (bases || []).forEach((base, i) => {
      pushTarget(base, { target: tgt, info: infos && infos[i], ubiquitous: false });
    });
  }

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
  const addonsBySlot = new Map();
  for (const a of addons) {
    const key = `${a.ownerKind}:${a.owner}:${a.slot}`;
    const list = addonsBySlot.get(key);
    if (list) list.push(a);
    else addonsBySlot.set(key, [a]);
  }

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
      toneFactors,
      quotePipelines,
      effectModes,
    },
  };
}
