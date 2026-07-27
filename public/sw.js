/* Service worker: makes neurarium installable (PWA) and usable offline.
 *
 * When online we ALWAYS contact the network, so a user never renders unchecked,
 * outdated data (or a stale ES module). The Cache-API copy is only a fallback for
 * when the network is unavailable (offline). It is deliberately NOT
 * stale-while-revalidate: SWR would answer from cache before confirming freshness,
 * which is unacceptable here.
 *
 * One strategy for everything (data, code and shell alike): EXPLICIT CONDITIONAL
 * REVALIDATION. We can't lean on the browser HTTP cache for cheap 304s, because a
 * plain `fetch()` inside a service worker does not reliably emit a conditional
 * request (it re-downloads the full 200). So we do it by hand: keep each cached
 * response's validator (`ETag` / `Last-Modified`) and send it back as
 * `If-None-Match` / `If-Modified-Since`. The server answers `304 Not Modified`
 * when unchanged (we serve the cached copy, zero body transferred) or a fresh
 * `200` when it actually changed (we cache + serve that). Always fresh, cheap
 * when unchanged.
 *
 * Code used to be plain network-first (re-download the full file every time) out
 * of caution about mixing a stale ES module with a fresh one on this no-build,
 * rsync-deployed site. That caution is satisfied by revalidation: every single
 * file is confirmed current with the server before it is used, so an old module
 * can never run. What it is NOT is a re-download of ~1 MB of code + shell on every
 * load, which is what made a phone reload crawl. (The residual "a deploy lands
 * mid-load" window is identical either way, and every online visit revalidates
 * the whole set together, so the offline fallback stays internally consistent:
 * all-old, never old+new.)
 *
 * Bump CACHE when the caching logic itself changes; activate() prunes older caches.
 */
const CACHE = "neurarium-v3";

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

// Explicit conditional revalidation: always contact the server, but cheaply. We
// forward the cached copy's validator so the server can answer a bodyless
// `304 Not Modified` when nothing changed (we then serve the cached copy) and a
// full `200` only when it did. `cache: "no-store"` bypasses the browser HTTP
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

  // Everything same-origin: revalidate (fresh, and free when unchanged). Offline,
  // `revalidate` already returns the cached copy; the catch below only handles the
  // case where there is nothing cached for this request at all.
  event.respondWith(
    revalidate(req).catch(async () => {
      // A navigation with nothing cached for it falls back to the app shell.
      if (req.mode === "navigate") {
        const shell = await caches.match("index.html");
        if (shell) return shell;
      }
      throw new Error("offline and not cached");
    })
  );
});
