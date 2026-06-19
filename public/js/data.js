// Loading of the brain dataset produced by generate_data.py.
//
// The viewer treats data/brain.jsonl as the source of "what to draw" and the
// shapes/*.json files as the source of "geometric form". This module fetches
// both and returns a single normalized object so the rest of the app never has
// to know about the on-disk layout.
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
 * @property {object[]} structures  Region records (type === "structure"), each
 *   augmented with a resolved `shape` payload from its shapes/<id>.json file.
 *   `name`/`base_name` are localized to plain strings (the full hemisphere name
 *   and the side-stripped legend label).
 * @property {object[]} projections Directed pathway records (type === "projection"),
 *   each augmented with a resolved `color` (from the kind->colour meta map); its
 *   `label`/`description`/`neurotransmitter` are localized to plain strings.
 * @property {object[]} circuits    Named circuit records (type === "circuit"):
 *   `{id, name, structures:[structure ids]}` (localized `name`). The arrows
 *   belonging to a circuit are derived in the viewer (both endpoints among
 *   `structures`).
 * @property {Map<string, object>} byId  structure id -> structure record.
 * @property {{projectionColors: Object<string,string>,
 *   groupLabels: Object<string,string>,
 *   kindLabels: Object<string,string>}} meta  Presentation maps emitted by the
 *   generator (kind->arrow colour, group->legend heading, kind->display label),
 *   so the dataset is self-describing rather than relying on hardcoded values in
 *   the viewer. `groupLabels`/`kindLabels` are localized to plain strings.
 */

/**
 * Load and assemble the whole dataset: the JSONL plus every referenced shape
 * file (fetched in parallel).
 * @param {string} [jsonlUrl="data/brain.jsonl"]
 * @returns {Promise<BrainData>}
 */
export async function loadBrainData(jsonlUrl = "data/brain.jsonl") {
  const text = await (await fetchOrThrow(jsonlUrl)).text();
  const records = parseJsonl(text);

  const structures = records.filter((r) => r.type === "structure");
  const projections = records.filter((r) => r.type === "projection");
  const circuits = records.filter((r) => r.type === "circuit");

  // Presentation maps emitted by the generator (kind->arrow colour,
  // group->legend heading, kind->display label), so the palette/headings live in
  // the data, not hardcoded in the viewer. The label maps are bilingual {en,fr};
  // localize their values to plain strings here (the colour map is neutral).
  const metaRecord = records.find((r) => r.type === "meta") || {};
  const projectionColors = metaRecord.projection_colors || {};
  const localizeMap = (m) =>
    Object.fromEntries(Object.entries(m || {}).map(([k, v]) => [k, localize(v)]));
  const groupLabels = localizeMap(metaRecord.group_labels);
  const kindLabels = localizeMap(metaRecord.kind_labels);

  // Resolve each projection's arrow colour from its kind (kept as the raw key,
  // since it indexes the colour/label maps), and localize its display fields so
  // the viewer reads plain strings.
  for (const p of projections) {
    p.color = projectionColors[p.kind] || "#ffffff";
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
  return {
    structures,
    projections,
    circuits,
    byId,
    meta: { projectionColors, groupLabels, kindLabels },
  };
}
