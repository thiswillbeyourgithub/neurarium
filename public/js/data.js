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
 * @typedef {Object} BrainData
 * @property {object[]} structures  Region records (type === "structure"), each
 *   augmented with a resolved `shape` payload from its shapes/<id>.json file.
 * @property {object[]} projections Directed pathway records (type === "projection").
 * @property {object[]} circuits    Named circuit records (type === "circuit"):
 *   `{id, name, structures:[structure ids]}`. The arrows belonging to a circuit
 *   are derived in the viewer (both endpoints among `structures`).
 * @property {Map<string, object>} byId  structure id -> structure record.
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

  // Fetch all shape files in parallel and attach them to their structure.
  await Promise.all(
    structures.map(async (s) => {
      s.shape = await (await fetchOrThrow(s.shape_file)).json();
    }),
  );

  const byId = new Map(structures.map((s) => [s.id, s]));
  return { structures, projections, circuits, byId };
}
