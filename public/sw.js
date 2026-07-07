/* Service worker: makes neurarium installable (PWA) and usable offline.
 *
 * Strategy is NETWORK-FIRST on purpose. The site is deployed by rsync with no
 * content-hashed filenames and Caddy sends `Cache-Control: no-store` precisely
 * so a stale ES module is never mixed with a fresh one (see docker/Caddyfile).
 * A cache-first worker would reintroduce exactly that hazard. So: when online we
 * always fetch the live asset (and refresh the cache copy); the cache is only a
 * fallback for when the network is unavailable. Because every online visit
 * rewrites the whole set together, the offline fallback stays internally
 * consistent (all-old, never old+new).
 *
 * Bump CACHE when the caching logic itself changes; activate() prunes older caches.
 */
const CACHE = "neurarium-v1";

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

self.addEventListener("fetch", (event) => {
  const req = event.request;
  // Only GET, and only our own origin: Wikipedia leads/images and any analytics
  // beacon pass straight through untouched (no respondWith == browser default).
  if (req.method !== "GET") return;
  if (new URL(req.url).origin !== self.location.origin) return;

  event.respondWith(
    fetch(req)
      .then((res) => {
        // Cache a copy of every good same-origin response for offline fallback.
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy));
        }
        return res;
      })
      .catch(async () => {
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
