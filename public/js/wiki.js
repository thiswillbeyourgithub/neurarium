// Runtime fetch of a Wikipedia article's lead summary, so the description shown in
// an info panel (a drug, a receptor, a structure, a non-receptor target: anything
// carrying a `wikipedia` link) reflects the *current* article.
//
// Why runtime: the panel text stays up to date with Wikipedia with no re-run/commit,
// and the dataset ships no copyrighted prose. Drugs, structures and non-receptor
// targets carry NO baked description: a fresh paragraph is inserted only once the
// live lead arrives. Receptors carry a short authored `description` painted first as
// the offline fallback, which this overrides best-effort when the live lead arrives.
// Any failure (offline, rate-limited, CSP-blocked, missing article) resolves to null
// and nothing changes, so the panel never breaks.
//
// Language: the viewer's locale wins. When the stored `wikipedia` article is in
// another language (links are authored as the English one), the locale article is
// resolved via the source wiki's langlinks; if the locale has no article the
// article's own-language (English) lead is used as the fallback.
//
// Requests are anonymous cross-origin GETs to the Wikimedia REST + action APIs
// (CORS-enabled, `credentials: omit`, no custom headers, so no preflight). The
// container CSP must allow these hosts (connect-src https://*.wikipedia.org, see
// docker/Caddyfile). Results are cached per drug+language (in-memory + a session
// store) so re-opening a drug never refetches.

// `${url}::${lang}` -> { text, lang } | null. A null (negative) result is cached
// in-memory only, so a page reload retries a transient failure; positives are also
// persisted to sessionStorage so a session never refetches the same lead.
const memCache = new Map();
const SS_PREFIX = "neurarium:wikilead:";

function ssGet(key) {
  try {
    const v = sessionStorage.getItem(SS_PREFIX + key);
    return v ? JSON.parse(v) : undefined;
  } catch {
    return undefined;
  }
}

function ssSet(key, val) {
  try {
    sessionStorage.setItem(SS_PREFIX + key, JSON.stringify(val));
  } catch {
    /* storage full / disabled: caching is best-effort */
  }
}

// "https://en.wikipedia.org/wiki/Citalopram" -> { lang: "en", title: "Citalopram" }
function parseArticle(url) {
  try {
    const u = new URL(url);
    const host = u.hostname.match(/^([a-z-]+)\.wikipedia\.org$/i);
    const path = u.pathname.match(/^\/wiki\/(.+)$/);
    if (!host || !path) return null;
    return {
      lang: host[1].toLowerCase(),
      title: decodeURIComponent(path[1]).replace(/_/g, " "),
    };
  } catch {
    return null;
  }
}

async function fetchJson(url) {
  const res = await fetch(url, { credentials: "omit", redirect: "follow" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// REST page/summary -> the plain-text lead extract (the article's lead paragraph).
async function summaryExtract(lang, title) {
  const url =
    `https://${lang}.wikipedia.org/api/rest_v1/page/summary/` +
    encodeURIComponent(title.replace(/ /g, "_"));
  const data = await fetchJson(url);
  const text = data && typeof data.extract === "string" ? data.extract.trim() : "";
  return text || null;
}

// Resolve `title`'s equivalent in `target` language via langlinks on the source
// wiki (the documented anonymous-CORS path uses origin=*). Returns the localized
// title, or null when the target language has no article.
async function langTitle(srcLang, title, target) {
  const url =
    `https://${srcLang}.wikipedia.org/w/api.php?action=query&prop=langlinks` +
    `&lllang=${encodeURIComponent(target)}&lllimit=1&redirects=1` +
    `&titles=${encodeURIComponent(title)}&format=json&origin=*`;
  const data = await fetchJson(url);
  const pages = data && data.query && data.query.pages;
  if (!pages) return null;
  for (const k of Object.keys(pages)) {
    const ll = pages[k].langlinks;
    if (ll && ll.length && ll[0]["*"]) return ll[0]["*"];
  }
  return null;
}

// Fetch the lead summary for the Wikipedia article at `wikipediaUrl` in `lang`,
// falling back to the article's own language (English) when the locale article is
// missing. Resolves to { text, lang } or null; never rejects (the caller keeps the
// baked description / no description on null).
export async function fetchWikiLead(wikipediaUrl, lang) {
  if (!wikipediaUrl) return null;
  const key = `${wikipediaUrl}::${lang}`;
  if (memCache.has(key)) return memCache.get(key);
  const cached = ssGet(key);
  if (cached !== undefined) {
    memCache.set(key, cached);
    return cached;
  }

  let result = null;
  try {
    const art = parseArticle(wikipediaUrl);
    if (art) {
      if (lang === art.lang) {
        const text = await summaryExtract(art.lang, art.title);
        if (text) result = { text, lang: art.lang };
      } else {
        // Locale differs from the article's wiki: try the locale article first,
        // else fall back to the article's own (English) lead.
        const localTitle_ = await langTitle(art.lang, art.title, lang).catch(() => null);
        const localized = localTitle_
          ? await summaryExtract(lang, localTitle_).catch(() => null)
          : null;
        if (localized) {
          result = { text: localized, lang };
        } else {
          const text = await summaryExtract(art.lang, art.title);
          if (text) result = { text, lang: art.lang };
        }
      }
    }
  } catch {
    result = null; // any failure -> baked description stands
  }

  memCache.set(key, result);
  if (result) ssSet(key, result); // persist positives only
  return result;
}
