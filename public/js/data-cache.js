// Version-keyed client cache of the fetched dataset (localStorage + gzip).
//
// The deploy serves the data with `Cache-Control: no-store` (see docker/Caddyfile)
// and the service worker is network-first, so without this the browser re-downloads
// the ~600 KB of core data on every visit. The dataset only ever changes when the
// app version bumps (version.js is the single source of truth, bumped per release,
// and data edits ship with a bump), so we cache the fetched docs keyed by
// `__APP_VERSION__`: a matching version is a guaranteed-fresh hit (zero network for
// data), a bumped version misses and re-fetches, and stale entries are pruned. This
// respects the "always fresh" intent while not paying for unchanged bytes.
//
// English and French fetch the same English-only core data; French additionally
// pulls the translations side table, so the cache is keyed by version + language and
// the French payload carries its translations. Values are gzip-compressed (via
// CompressionStream, base64-wrapped) so both languages fit comfortably under the
// localStorage quota; on a browser without CompressionStream we store the raw JSON
// (and simply skip caching if that would blow the quota). Made with the help of
// Claude Code.

const PREFIX = "neurarium-data:";

function appVersion() {
  return (typeof window !== "undefined" && window.__APP_VERSION__) || "dev";
}

function cacheKey(lang) {
  return `${PREFIX}${appVersion()}:${lang || "en"}`;
}

// On a dev host the version rarely bumps between data edits, so caching would serve
// stale data. Bypass the cache there; production hosts get the version-keyed cache.
function isDevHost() {
  if (typeof location === "undefined") return true;
  const h = location.hostname;
  return h === "localhost" || h === "127.0.0.1" || h === "[::1]" || h === "";
}

function hasStorage() {
  try {
    return typeof localStorage !== "undefined";
  } catch {
    return false; // localStorage can throw (privacy mode, sandboxed iframe).
  }
}

async function gzipToBase64(str) {
  if (typeof CompressionStream === "undefined") return { enc: "raw", data: str };
  const stream = new Blob([str]).stream().pipeThrough(new CompressionStream("gzip"));
  const buf = await new Response(stream).arrayBuffer();
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return { enc: "gzip", data: btoa(bin) };
}

async function base64ToJson(rec) {
  if (rec.enc !== "gzip") return rec.data;
  const bin = atob(rec.data);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  return await new Response(stream).text();
}

// Drop every cache entry that is not for the current version (both languages of the
// current version are kept). Called before a write so old versions never accumulate.
function pruneOtherVersions() {
  try {
    const keep = new Set([cacheKey("en"), cacheKey("fr")]);
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k && k.startsWith(PREFIX) && !keep.has(k)) localStorage.removeItem(k);
    }
  } catch {
    /* best-effort */
  }
}

/**
 * Read the cached dataset for `lang`, or null on a miss / any failure (dev host,
 * no storage, version bump, corrupt entry, decompression error). Never throws.
 * @param {string} lang  Active language ("en" / "fr").
 * @returns {Promise<object|null>}
 */
export async function readDataCache(lang) {
  if (isDevHost() || !hasStorage()) return null;
  try {
    const raw = localStorage.getItem(cacheKey(lang));
    if (!raw) return null;
    return JSON.parse(await base64ToJson(JSON.parse(raw)));
  } catch {
    return null;
  }
}

/**
 * Store the freshly fetched dataset for `lang`. Best-effort: a quota error or a
 * browser without CompressionStream just leaves the cache unpopulated (the app
 * falls back to fetching next time). Never throws.
 * @param {string} lang     Active language ("en" / "fr").
 * @param {object} payload  The raw fetched docs to cache.
 */
export async function writeDataCache(lang, payload) {
  if (isDevHost() || !hasStorage()) return;
  try {
    pruneOtherVersions();
    const rec = await gzipToBase64(JSON.stringify(payload));
    localStorage.setItem(cacheKey(lang), JSON.stringify(rec));
  } catch {
    /* quota exceeded or unsupported: skip caching, not fatal */
  }
}
