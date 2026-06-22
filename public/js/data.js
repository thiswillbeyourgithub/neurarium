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
 *   `{id, name, structures:[structure ids]}` (localized `name`). The arrows
 *   belonging to a circuit are derived in the viewer (both endpoints among
 *   `structures`).
 * @property {object[]} receptors  Neurotransmitter receptor records (from
 *   receptors.jsonl). Each is augmented with localized `neurotransmitter` /
 *   `description`, a resolved `familyLabel` / `classLabel` / `signLabel` /
 *   `synapticLabel` and `signColor`, the concrete `structureIds` its `locations`
 *   bases expand to (every structure when `ubiquitous`), the side-stripped
 *   `locationNames`, and a `focusable` flag (false for the inert "stub" receptors).
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
 *   localized `note`, and the concrete `structureIds` it lights), the union
 *   `structureIds` the focus dims to, a `focusable` flag and search `keywords`.
 * @property {Map<string, object>} byId  structure id -> structure record.
 * @property {{projectionColors: Object<string,string>,
 *   groupLabels: Object<string,string>,
 *   kindLabels: Object<string,string>,
 *   signColors: Object<string,string>,
 *   signLabels: Object<string,string>}} meta  Presentation maps emitted by the
 *   generator (kind->arrow colour, group->legend heading, kind->display label,
 *   and the excit/inhib sign colour + heading for the colour-mode toggle), so the
 *   dataset is self-describing rather than relying on hardcoded values in the
 *   viewer. `groupLabels`/`kindLabels`/`signLabels` are localized to plain strings.
 */

/**
 * Load and assemble the whole dataset: the per-type data files (meta.json +
 * structures/projections/circuits.jsonl) plus every referenced shape file, all
 * fetched in parallel.
 * @param {string} [dataDir="data"] Directory the data files live under.
 * @returns {Promise<BrainData>}
 */
export async function loadBrainData(dataDir = "data") {
  const [metaRecord, structures, projections, circuits, receptors, drugs] =
    await Promise.all([
      fetchOrThrow(`${dataDir}/meta.json`).then((r) => r.json()),
      fetchJsonl(`${dataDir}/structures.jsonl`),
      fetchJsonl(`${dataDir}/projections.jsonl`),
      fetchJsonl(`${dataDir}/circuits.jsonl`),
      fetchJsonl(`${dataDir}/receptors.jsonl`),
      fetchJsonl(`${dataDir}/drugs.jsonl`),
    ]);

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

  // Resolve each projection's colours from its kind (kept as the raw key, since it
  // indexes the colour/label maps): `color` is the per-transmitter colour (default
  // mode), `sign`/`signColor` the coarse excitatory/inhibitory view the colour
  // toggle switches to. Localize the display fields so the viewer reads plain
  // strings.
  for (const p of projections) {
    p.color = projectionColors[p.kind] || "#ffffff";
    p.sign = kindSigns[p.kind] || "modulatory";
    p.signColor = signColors[p.sign] || "#ffffff";
    p.label = localize(p.label);
    p.description = localize(p.description);
    p.neurotransmitter = localize(p.neurotransmitter);
  }

  // Localize the structure + circuit display strings (the geometry/ids stay as
  // language-neutral keys).
  for (const s of structures) {
    s.name = localize(s.name);
    s.base_name = localize(s.base_name);
  }
  for (const c of circuits) {
    c.name = localize(c.name);
  }

  // Fetch all shape files in parallel and attach them to their structure.
  await Promise.all(
    structures.map(async (s) => {
      s.shape = await (await fetchOrThrow(s.shape_file)).json();
    }),
  );

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
  for (const d of drugs) {
    d.description = d.description ? localize(d.description) : "";
    d.nbn = d.nbn ? localize(d.nbn) : "";
    d.categoryLabels = (d.categories || []).map((c) => drugCategoryLabels[c] || c);
    d.category = d.categoryLabels[0] || "";
    const affected = new Set();
    d.bindings = (d.bindings || []).map((b) => {
      const tgt = drugTargets[b.target] || {};
      const act = drugActions[b.action] || {};
      const effect = b.effect || act.effect || "modulate";
      let structureIds;
      if (tgt.ubiquitous) {
        structureIds = allIds.slice();
      } else if (tgt.receptor && receptorStructureIds.has(tgt.receptor)) {
        structureIds = receptorStructureIds.get(tgt.receptor).slice();
      } else {
        structureIds = (tgt.regions || []).flatMap((bse) =>
          [bse, `${bse}_R`, `${bse}_L`].filter((id) => byId.has(id)),
        );
      }
      for (const id of structureIds) affected.add(id);
      return {
        target: b.target,
        targetName: tgt.name ? localize(tgt.name) : b.target,
        system: tgt.system || null,
        receptor: tgt.receptor || null,
        action: b.action,
        actionLabel: act.label ? localize(act.label) : b.action,
        effect,
        effectColor: drugEffectColors[effect] || "#ffffff",
        effectLabel: drugEffectLabels[effect] || effect,
        note: b.note ? localize(b.note) : "",
        tentative: !!b.tentative,
        structureIds,
      };
    });
    d.structureIds = [...affected];
    // Focusable if it carries any binding (the info panel + search work even when
    // a target has no modeled region to light); the generator already cleared it
    // for a drug with no bindings at all.
    d.focusable = !!d.focusable && d.bindings.length > 0;
    d.keywords = [...d.categoryLabels, d.nbn, ...d.bindings.map((b) => b.targetName)]
      .filter(Boolean)
      .join(" ");
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
      locationNames: (tgt.regions || []).map((b) => baseName.get(b) || b),
      // The raw base ids parallel to locationNames, so the panel can make each
      // "Found in" row jump to that structure (the receptor records keep their own
      // `locations` for the same purpose).
      locationBases: (tgt.regions || []).slice(),
      keywords: [typeLabel, systemLabel].filter(Boolean).join(" "),
    });
  }

  return {
    structures,
    projections,
    circuits,
    receptors,
    targets,
    drugs,
    byId,
    meta: {
      projectionColors,
      groupLabels,
      kindLabels,
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
    },
  };
}
