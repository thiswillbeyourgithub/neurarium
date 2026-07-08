/* Service worker: makes neurarium installable (PWA) and usable offline.
 *
 * When online we ALWAYS contact the network, so a user never renders unchecked,
 * outdated data (or a stale ES module). The Cache-API copy is only a fallback for
 * when the network is unavailable (offline). It is deliberately NOT
 * stale-while-revalidate: SWR would answer from cache before confirming freshness,
 * which is unacceptable here.
 *
 * Two strategies, split by what the asset IS:
 *
 * - DATA (/data/*, incl. shapes): EXPLICIT CONDITIONAL REVALIDATION. We can't lean
 *   on the browser HTTP cache for cheap 304s, because a plain `fetch()` inside a
 *   service worker does not reliably emit a conditional request (it re-downloads
 *   the full 200). So we do it by hand: keep each cached response's validator
 *   (`ETag` / `Last-Modified`) and send it back as `If-None-Match` /
 *   `If-Modified-Since`. The server answers `304 Not Modified` when unchanged (we
 *   serve the cached copy, zero body transferred) or a fresh `200` when it actually
 *   changed (we cache + serve that). Always fresh, cheap when unchanged.
 * - CODE + shell (js/*, index.html, vendor, ...): plain NETWORK-FIRST (always
 *   refetch the full file). No conditional revalidation: `no-store` + a full
 *   refetch keeps the "never mix a stale module with a fresh one" guarantee the
 *   no-build rsync deploy relies on. Cache-API copy is the offline fallback only.
 *
 * Because every online visit revalidates the whole set together, the offline
 * fallback stays internally consistent (all-old, never old+new).
 *
 * Bump CACHE when the caching logic itself changes; activate() prunes older caches.
 */
const CACHE = "neurarium-v2";

// Minimal app shell precached on install so a first offline launch has a page +
// icons even before anything else was visited. The bulk of assets (js/*, data/*,
// vendor/*) are cached opportunistically by the fetch handler as they load.
const SHELL = [
  ".",
  "index.html",
  "manifest.webmanifest",
  "favicon.svg",
  "icon-192.png",
  "icon-512.png",
];

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      // Best-effort: a failed shell fetch must not abort the whole install.
      Promise.allSettled(SHELL.map((url) => cache.add(url)))
    )
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

// Fetch the request fresh and cache a copy of any good response (offline copy).
// Returns the live response; rejects if the network is unavailable.
async function fetchAndCache(req) {
  const res = await fetch(req);
  if (res && res.ok) {
    const cache = await caches.open(CACHE);
    await cache.put(req, res.clone());
  }
  return res;
}

// Explicit conditional revalidation for the dataset: always contact the server,
// but cheaply. We forward the cached copy's validator so the server can answer a
// bodyless `304 Not Modified` when nothing changed (we then serve the cached copy)
// and a full `200` only when it did. `cache: "no-store"` bypasses the browser HTTP
// cache so OUR conditional headers are the only ones in play (a plain fetch would
// otherwise just re-download the full body). Falls back to the cached copy offline.
async function revalidate(req) {
  const cached = await caches.match(req);
  const headers = new Headers();
  if (cached) {
    const etag = cached.headers.get("ETag");
    const lastMod = cached.headers.get("Last-Modified");
    if (etag) headers.set("If-None-Match", etag);
    else if (lastMod) headers.set("If-Modified-Since", lastMod);
  }
  let res;
  try {
    res = await fetch(new Request(req.url, { headers, cache: "no-store" }));
  } catch (err) {
    if (cached) return cached; // offline: last-known copy
    throw err;
  }
  if (res.status === 304 && cached) return cached; // unchanged: cheap hit
  if (res.ok) {
    const cache = await caches.open(CACHE);
    await cache.put(req, res.clone());
  }
  return res;
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  // Only GET, and only our own origin: Wikipedia leads/images and any analytics
  // beacon pass straight through untouched (no respondWith == browser default).
  if (req.method !== "GET") return;
  if (new URL(req.url).origin !== self.location.origin) return;

  // Dataset (+ shapes): explicit conditional revalidation (fresh, cheap 304s).
  if (new URL(req.url).pathname.startsWith("/data/")) {
    event.respondWith(revalidate(req));
    return;
  }

  // Code + shell: network-first (always refetch the full file); the Cache-API copy
  // is the offline fallback only.
  event.respondWith(
    fetchAndCache(req).catch(async () => {
      const cached = await caches.match(req);
      if (cached) return cached;
      // A navigation with nothing cached for it falls back to the app shell.
      if (req.mode === "navigate") {
        const shell = await caches.match("index.html");
        if (shell) return shell;
      }
      throw new Error("offline and not cached");
    })
  );
});
