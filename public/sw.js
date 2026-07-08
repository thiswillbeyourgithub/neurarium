/* Service worker: makes neurarium installable (PWA) and usable offline.
 *
 * Two strategies, split by what the asset IS:
 *
 * - CODE + shell (html, js, vendor, icons, ...): NETWORK-FIRST. The site is
 *   rsync-deployed with no content-hashed filenames and Caddy sends
 *   `Cache-Control: no-store` (see docker/Caddyfile) precisely so a stale ES
 *   module is never mixed with a fresh one. A cache-first worker would reintroduce
 *   that hazard, so when online we always fetch live code (refreshing the cache
 *   copy); the cache is only an offline fallback.
 *
 * - DATA + shapes (everything under `/data/`): STALE-WHILE-REVALIDATE. This is the
 *   heavy payload (~600 KB of jsonl/meta + the shape files) and it is pure DATA,
 *   not executable code, so a momentarily one-load-stale set is harmless (the app
 *   tolerates a mismatch: e.g. an unresolved quote just renders no tooltip). So on
 *   a repeat visit we serve the cached copy INSTANTLY (fast + reliable on a slow or
 *   flaky link, which network-first is not) and refresh the cache from the network
 *   in the BACKGROUND for next time. No version key is involved: the cache
 *   self-updates whenever the network has new bytes, so nothing can be forgotten.
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

// Fetch the request and cache a copy of any good response (for offline + SWR).
// Returns the live response; rejects if the network is unavailable.
async function fetchAndCache(req) {
  const res = await fetch(req);
  if (res && res.ok) {
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

  const isData = new URL(req.url).pathname.includes("/data/");

  if (isData) {
    // STALE-WHILE-REVALIDATE for data + shapes: kick off the network refresh (and
    // keep the worker alive for it via waitUntil), but answer from cache the
    // instant a cached copy exists so a repeat visit is fast even on a slow link.
    // A cold cache falls through to the same in-flight network promise.
    const network = fetchAndCache(req).catch(() => null);
    event.waitUntil(network);
    event.respondWith(
      caches.match(req).then((cached) => {
        if (cached) return cached;
        return network.then((res) => {
          if (res) return res;
          throw new Error("offline and not cached");
        });
      })
    );
    return;
  }

  // NETWORK-FIRST for code + shell: always fetch live when online (refreshing the
  // cache copy); fall back to cache only when the network is unavailable.
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
