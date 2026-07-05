# Analytics & dev banner

> Reference detail moved out of [`CLAUDE.md`](../CLAUDE.md) to keep that file a terse map. This is the full text for this subsystem.

## Analytics (umami)

Optional, privacy-friendly. Because this is a no-build static site on a read-only
rootfs, config is injected at runtime:

1. Set `ANALYTICS_URL`, `ANALYTICS_WEBSITE_ID`, optional `ANALYTICS_SRI`,
   `ANALYTICS_DNT` (umami `data-do-not-track`, default `"true"`) in `docker/.env`.
2. `docker/entrypoint.sh` renders `/gen/app-config.js` from those vars at start;
   Caddy serves it for `/app-config.js`.
3. `js/app-init.js` reads `window.__APP_CONFIG__` and injects the umami `<script>`
   (with SRI/crossorigin + explicit `data-do-not-track`).

Client-facing names are generic (`app-config.js`, `js/app-init.js`,
`__APP_CONFIG__`) because a path containing "analytics" is blocked by many content
filters/proxies. Leave the URL/ID empty to fully disable. `ANALYTICS_URL` must be
the tracker *script* URL (used as a `<script src>`); the container validates at
startup that it is reachable and serves JavaScript, else it crashes (so a
misconfiguration is loud, not silently tracking nothing).

## Dev / WIP banner

Optional "work in progress" top banner, same runtime-injection plumbing as
analytics. `DEV` in `docker/.env` (default 0); `entrypoint.sh` stamps
`STARTED_AT=$(date +%s)` and renders both into `/gen/app-config.js`.
`js/dev-banner.js` reveals `#dev-banner` (amber, in `#banners`) when `dev === "1"`
and computes "X ago" from `startedAt` (refreshed per minute). Clicking dismisses it
for the current view only (not persisted, so a reload brings it back). It ends with
a **Source** link to `cfg.sourceUrl` (`SOURCE_URL` env, default the public site;
only `http(s)`; clicking the link navigates instead of dismissing). The repo URL is
not hardcoded in committed source.
