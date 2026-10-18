// Network helpers for the data loader: JSONL parsing, fetch-or-throw, where the
// build-time derived files sit, and the lazily fetched bilingual search names.

// Repeat-visit speed/offline resilience for these files is handled by the service
// worker (stale-while-revalidate for /data/*, see public/sw.js), not here.

/**
 * Parse JSONL text (one JSON object per line) into an array, skipping blank
 * lines. Kept tiny and dependency-free on purpose.
 * @param {string} text
 * @returns {object[]}
 */
export function parseJsonl(text) {
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
export async function fetchOrThrow(url) {
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
export async function fetchJsonl(url) {
  return parseJsonl(await (await fetchOrThrow(url)).text());
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
