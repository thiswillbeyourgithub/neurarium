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
 * Rehydrate externalized source quotes in place. The emitted data replaces every
 * quote-bearing source with a `{quote_id, provenance}` reference and stores the
 * excerpt once in quotes.jsonl (see quote_table.py). This deep-walk merges the
 * quote node's `corpus`/`page`/`quote`/`species`/`llm` fields back onto each reference,
 * so downstream code reads `source.quote` etc. exactly as before. A dangling
 * `quote_id` (no matching quote) is left as-is (check_data.py guards against it).
 * @param {*} node       Any value (object/array/scalar) to walk.
 * @param {object} byId  quote_id -> quote node map.
 */
function rehydrateQuotes(node, byId) {
  if (Array.isArray(node)) {
    for (const v of node) rehydrateQuotes(v, byId);
  } else if (node && typeof node === "object") {
    if (typeof node.quote_id === "string") {
      const q = byId[node.quote_id];
      if (q) {
        for (const k of ["corpus", "page", "quote", "species", "llm"]) {
          if (k in q) node[k] = q[k];
        }
      }
    }
    for (const k in node) rehydrateQuotes(node[k], byId);
  }
}

/**
 * Resolve a translatable field to the chosen language. The data file stores
 * translatable strings as `{en, fr}` objects (see generate_data.py's `_t`);
 * `window.__I18N__.pick` collapses one to the active language. A plain string
 * passes straight through, and if i18n hasn't loaded we fall back to the English
 * member, so the rest of the viewer can treat every name/label as a plain string.
 * @param {string|{en?:string,fr?:string}} field
 * @returns {string}
 */
function localize(field) {
  if (window.__I18N__) return window.__I18N__.pick(field);
  if (field && typeof field === "object") return field.en ?? field;
  return field;
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
 * @property {object[]} drugs  Drug records (from drugs.jsonl, sourced from Stahl's
 *   Prescriber's Guide). Each is augmented with localized `description` / `nbn`,
 *   `categoryLabels` (+ primary `category`), and resolved `bindings` (each binding
 *   carrying `targetName`, `actionLabel`, net `effect` + `effectColor`/`effectLabel`,
 *   localized `note`, an `affinityWeight` (0.35..1, Ki-derived engagement) + signed
 *   `toneSign`, and the concrete `structureIds` it lights), the union
 *   `structureIds` the focus dims to, `flowSystems` (kind -> {direction, weight},
 *   the signed affinity-weighted per-system flow tone), a `focusable` flag and search `keywords`,
 *   plus a `structureImage` (the vendored molecular-structure SVG path, or null).
 * @property {Map<string, {drug: object, binding: object}[]>} drugsByTarget
 *   Reverse index: a target id (a receptor id or a drug_targets key, matching each
 *   `targets` entry's id) -> the drugs that act on it, each paired with its resolved
 *   binding (its net-effect colour + action), deduped to one row per (drug, target).
 *   Lets a receptor / target panel list its interacting drugs grouped by category.
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

/**
 * Load and assemble the whole dataset: the per-type data files (meta.json +
 * structures/projections/circuits.jsonl) plus every referenced shape file, all
 * fetched in parallel.
 * @param {string} [dataDir="data"] Directory the data files live under.
 * @returns {Promise<BrainData>}
 */
export async function loadBrainData(dataDir = "data", onProgress = null) {
  onProgress?.({ stage: "meta" });
  // The emitted data is English-only; the French translations live in a single
  // side table (data/translations.fr.json) that `window.__I18N__.pick` looks each
  // English string up in. Fetch + install it BEFORE any localize() runs, and ONLY
  // in French (English users never request it, and it stays an empty table). A
  // failed fetch is non-fatal: pick() then falls back to the English strings.
  if (window.__I18N__ && window.__I18N__.lang === "fr") {
    try {
      const tr = await (await fetchOrThrow(`${dataDir}/translations.fr.json`)).json();
      window.__I18N__.setDataTranslations(tr);
    } catch (e) {
      console.error("Could not load French translations; showing English data.", e);
    }
  }
  const [metaRecord, structures, projections, circuits, projectionGroups,
         receptors, drugs, quotes] =
    await Promise.all([
      fetchOrThrow(`${dataDir}/meta.json`).then((r) => r.json()),
      fetchJsonl(`${dataDir}/structures.jsonl`),
      fetchJsonl(`${dataDir}/projections.jsonl`),
      fetchJsonl(`${dataDir}/circuits.jsonl`),
      fetchJsonl(`${dataDir}/projection_groups.jsonl`),
      fetchJsonl(`${dataDir}/receptors.jsonl`),
      fetchJsonl(`${dataDir}/drugs.jsonl`),
      fetchJsonl(`${dataDir}/quotes.jsonl`),
    ]);
  // Source quotes are emitted once into quotes.jsonl (deduplicated), each node
  // carrying only a `{quote_id, provenance}` reference (see quote_table.py).
  // Rehydrate every reference in place BEFORE any downstream use, so the rest of
  // the viewer sees each source with its `corpus`/`page`/`quote`/`species` fields
  // as if they had been emitted inline. The `provenance` grade stays on the node.
  const quotesById = Object.create(null);
  for (const q of quotes) quotesById[q.id] = q;
  rehydrateQuotes([metaRecord, structures, projections, circuits,
                   projectionGroups, receptors, drugs], quotesById);
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
  const drugTargets = metaRecord.drug_targets || {};
  const drugActions = metaRecord.drug_actions || {};
  const drugEffectColors = metaRecord.drug_effect_colors || {};
  const drugEffectLabels = localizeMap(metaRecord.drug_effect_labels);
  // Drug target system -> projection kind, for the per-drug "by-mechanism flow"
  // overlay (only the diffuse ascending modulatory systems are mapped; see
  // generate_data.py SYSTEM_FLOW_KINDS). Language-neutral, applied per drug below.
  const systemFlowKinds = metaRecord.system_flow_kinds || {};
  // Source corpora (id -> {short, citation, url, pages_dir}) the per-claim binding
  // sources cite; the drug panel resolves a binding source's `corpus` to this for
  // its tooltip ref (see SOURCE_CORPORA in generate_data.py). Raw map (citation is
  // language-neutral); pages_dir is author-side and ignored by the viewer.
  const sourceCorpora = metaRecord.source_corpora || {};
  // Programmatic sourcing tally (per kind + headline) for the About panel; passed
  // through as-is (the numbers are computed in generate_data.py, see
  // _provenance_stats). Null on a dataset that predates it.
  const provenanceStats = metaRecord.provenance_stats || null;

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
  const locationEntry = (base, name, sources) => {
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
      species,
      nonHuman: !!species && species !== "Human",
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
  {
    let loaded = 0;
    const total = structures.length;
    onProgress?.({ stage: "shapes", loaded, total });
    await Promise.all(
      structures.map(async (s) => {
        s.shape = await (await fetchOrThrow(s.shape_file)).json();
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
    r.locationInfo = r.locations.map((b, i) =>
      locationEntry(b, r.locationNames[i], locSrc[b]));
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
  // Affinity -> a 0.35..1 engagement weight from the measured Ki (a pKi ramp:
  // sub-nanomolar ~1, micromolar ~0.35), NOT an effect-magnitude claim. Drives dot
  // density/size (drug-anim) and per-system flow intensity. A binding with no Ki
  // gets a neutral mid weight so it still animates.
  const AFFINITY_DEFAULT = 0.55;
  const affinityWeightOf = (ki) => {
    if (!ki || !(ki.median > 0)) return AFFINITY_DEFAULT;
    const pKi = 9 - Math.log10(ki.median); // median is in nM
    const t = Math.max(0, Math.min(1, (pKi - 6) / 4)); // 1 uM..0.1 nM -> 0..1
    return 0.35 + 0.65 * t;
  };
  // Signed tone contribution of one binding to its system's ascending flow (the
  // "Tone-setters + autoreceptors" model): +1 raises the transmitter's tone, -1
  // lowers it, 0 = not a tone-setter (a postsynaptic receptor -> dots only). Direction
  // comes from target type + action (+ autoreceptor sign for presynaptic receptors),
  // NOT from receptor class (a postsynaptic gain claim we deliberately do not make).
  const toneSignOf = (tgt, action) => {
    const type = tgt.type || "";
    if (type === "transporter") {
      // A vesicular transporter (VMAT2, flagged in meta.drug_targets) loads
      // vesicles, so inhibiting it *depletes* the transmitter and lowers tone, the
      // opposite of a plasma-membrane reuptake transporter (SERT/DAT/NET).
      if (tgt.vesicular) return action === "vesicular_inhibitor" || action === "blocker" ? -1 : 0;
      return action === "reuptake_inhibitor" || action === "releaser" ? 1 : 0;
    }
    if (type === "enzyme") return action === "enzyme_inhibitor" ? 1 : 0;
    if (type === "vesicle_protein") return action === "blocker" ? -1 : 0;
    if (type === "receptor" || type === "receptor_group") {
      // Sign/synaptic from the specific receptor record (a modeled 5-HT1x / D2/D3),
      // else from the group's own flag (the α2 family, carried in meta.drug_targets).
      const rm = tgt.receptor ? receptorMeta.get(tgt.receptor) : tgt;
      const presyn = rm && (rm.synaptic === "presynaptic" || rm.synaptic === "both");
      if (presyn && rm.sign === "inhibitory") {
        if (action === "agonist" || action === "partial_agonist") return -1;
        if (action === "antagonist" || action === "inverse_agonist") return 1;
      }
    }
    return 0;
  };
  // Normalize a quote-level sources list (a binding's `sources` or a drug's
  // `nbn_sources`) into the shape the panel renders.
  const mapSources = (sources) =>
    (sources || []).map((s) => ({
      corpus: s.corpus,
      page: s.page != null ? s.page : null,
      quote: s.quote || "",
      provenance: s.provenance || "llm",
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
    const act = affinityOnly ? {} : drugActions[b.action] || {};
    const effect = affinityOnly ? null : b.effect || act.effect || "modulate";
    return {
      tgt,
      affinityOnly,
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
      ki: resolveKi(b.ki),
    };
  };
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
    const affected = new Set();
    d.bindings = (d.bindings || []).map((b) => {
      // Display + provenance fields come from the shared resolver; the drug loop
      // then layers on the animation-only fields (structureIds/flow/weights). See
      // bindingDisplayFields. `tgt` is reused, `disp.tgt` is not returned to callers.
      const disp = bindingDisplayFields(b);
      const { tgt, affinityOnly, effect } = disp;
      // An affinity_only binding is PDSP-derived with no known direction: it is
      // listed in the panel (with its Ki) but has no action/effect and never
      // animates, so it contributes nothing to the lit-region union or flow.
      let structureIds = [];
      if (affinityOnly) {
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
      if (!affinityOnly) for (const id of structureIds) affected.add(id);
      return {
        target: disp.target,
        targetName: disp.targetName,
        system: disp.system,
        // The projection kind this binding's target system feeds (meta.system_flow_
        // kinds), null when the system has no modeled ascending pathway or the
        // binding is affinity-only. Lets a panel list the "projections affected" per
        // binding and lets d.flowKinds below dedupe from a single field.
        flowKind: affinityOnly ? null : systemFlowKinds[tgt.system] || null,
        receptor: disp.receptor,
        affinityOnly,
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
        affinityWeight: affinityOnly ? 0 : affinityWeightOf(b.ki),
        // Signed tone-setter contribution to its system's ascending flow (+1 raises
        // the transmitter's tone, -1 lowers, 0 = not a tone-setter -> dots only).
        toneSign: affinityOnly ? 0 : toneSignOf(tgt, b.action),
        // Per-claim sources ({corpus, page, quote, provenance}); `provenance` is the
        // strongest grade among the quote sources AND the measured Ki. See
        // bindingDisplayFields / _binding_grade in generate_data.py.
        sources: disp.sources,
        provenance: disp.provenance,
        // The measured PDSP Ki (own verified badge), null when absent.
        ki: disp.ki,
      };
    });
    d.structureIds = [...affected];
    // By-mechanism flow, split from the dots (approach 3): a projection kind gets a
    // flow overlay ONLY from *tone-setter* bindings (transporters, enzymes, vesicle
    // proteins, presynaptic inhibitory autoreceptors), never from a postsynaptic
    // receptor (those stay dots). Per engaged kind we sum toneSign*affinityWeight so
    // combos and opposing autoreceptors resolve to a net signed tone; the sign is the
    // flow direction (boost vs damp) and the clamped magnitude its intensity.
    const flowAcc = new Map();
    for (const b of d.bindings) {
      if (!b.flowKind || !b.toneSign) continue;
      flowAcc.set(b.flowKind, (flowAcc.get(b.flowKind) || 0) + b.toneSign * b.affinityWeight);
    }
    d.flowSystems = {};
    for (const [kind, sum] of flowAcc) {
      if (!sum) continue;
      d.flowSystems[kind] = { direction: sum > 0 ? 1 : -1, weight: Math.min(1, Math.abs(sum)) };
    }
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
    // the panel's "Projections affected" list. Empty for a drug that sets no tone (a
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
    // Focusable if it carries any binding (the info panel + search work even when
    // a target has no modeled region to light); the generator already cleared it
    // for a drug with no bindings at all.
    d.focusable = !!d.focusable && d.bindings.length > 0;
    // Commercial brand names, ordered for THIS locale (the `region` tag orders only,
    // it is never shown): a French reader sees fr -> eu -> na, everyone else
    // na -> eu -> fr; within a region the authored order is kept (first = most iconic).
    // `brandsOrdered` are the graded brand nodes in that order (deduped by name so a
    // name shared across regions shows once, keeping its first/top-region source);
    // `primaryBrand` is the single most-iconic name shown after the drug name
    // everywhere (see drugDisplayName), `brandNames` the full list, `displayName` the
    // name + primary. All brand names also feed search. See CLAUDE.md "Drugs".
    const brandRank = (window.__I18N__ && window.__I18N__.lang === "fr")
      ? { fr: 0, eu: 1, na: 2 }
      : { na: 0, eu: 1, fr: 2 };
    const brandSeen = new Set();
    d.brandsOrdered = (d.brands || [])
      .map((b, i) => ({ b, r: brandRank[b.region] ?? 9, i }))
      .sort((x, y) => x.r - y.r || x.i - y.i)
      .map((x) => x.b)
      .filter((b) => {
        const k = (b.name || "").toLowerCase();
        if (!k || brandSeen.has(k)) return false;
        brandSeen.add(k);
        return true;
      });
    d.brandNames = d.brandsOrdered.map((b) => b.name);
    d.primaryBrand = d.brandNames[0] || null;
    d.displayName = d.primaryBrand ? `${d.name} (${d.primaryBrand})` : d.name;
    d.keywords = [...d.categoryLabels, d.nbn, ...d.brandNames,
                  ...d.bindings.map((b) => b.targetName)]
      .filter(Boolean)
      .join(" ");
  }

  // Combo drugs ("A + B", or "A-B" with an en/em dash): resolve the constituents to
  // our standalone drug ids where they exist, so the panel warns it is a combination
  // and links out to each part (interactions between them may exist). Derived from
  // the name, not stored (matching the generator, which leaves combos untouched).
  const normName = (s) => (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const drugIdSet = new Set(drugs.map((d) => d.id));
  const drugByNorm = new Map(drugs.map((d) => [normName(d.name), d.id]));
  for (const d of drugs) {
    const parts = /[+–—]/.test(d.name || "")
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
  for (const d of drugs) {
    d.metabolites = (d.metabolites || []).map((m) => {
      const linkedId = m.drug_id || drugByNorm.get(normName(m.name)) || null;
      const linked = linkedId ? drugById.get(linkedId) || null : null;
      const ownBindings = (m.bindings || []).map((b) => {
        // Drop the resolver's `tgt` scratch field; keep only display/provenance.
        const { tgt, ...disp } = bindingDisplayFields(b);
        void tgt;
        return disp;
      });
      return {
        name: m.name,
        drugId: linkedId,
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
      };
    });
  }

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
  // (folded metabolite name, target) and merge the parents into `viaMetaboliteOfList`,
  // so the panel reads "metab. of A, B" once instead of listing the same molecule
  // twice. Persists across the outer drug loop (a shared metabolite is visited under
  // each parent).
  const metabRowByKey = new Map();
  for (const d of drugs) {
    const seen = new Set();
    for (const b of d.bindings) {
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
        const rowKey = `${normName(m.name)}:${b.target}`;
        const existing = metabRowByKey.get(rowKey);
        if (existing) {
          // Same metabolite, same target, different parent: merge the prodrug into the
          // existing row rather than adding a duplicate. (The bindings are identical
          // across parents, guarded by check_data, so keeping the first is safe.)
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
        locationEntry(b, baseName.get(b) || b, (tgt.location_sources || {})[b])),
      keywords: [typeLabel, systemLabel].filter(Boolean).join(" "),
    });
  }

  return {
    structures,
    projections,
    circuits,
    projectionGroups,
    projectionGroupsByKey,
    receptors,
    targets,
    drugs,
    drugsByTarget,
    byId,
    meta: {
      projectionColors,
      groupLabels,
      kindLabels,
      systemFlowKinds,
      signColors,
      signLabels,
      receptorFamilyLabels,
      receptorClassLabels,
      synapticLabels,
      targetTypeLabels,
      targetTypeColors,
      drugCategoryLabels,
      drugEffectColors,
      drugEffectLabels,
      sourceCorpora,
      provenanceStats,
    },
  };
}
