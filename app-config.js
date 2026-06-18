// Runtime app configuration: the optional umami metrics tag plus the optional
// "work in progress" dev banner.
//
// Named generically on purpose: a file/path containing "analytics" (or "track",
// "stats", ...) gets blocked by many content filters and forward proxies (e.g.
// Squid blocklists), which would 404 it before it reaches the browser. Keeping
// the URL neutral lets the request through; js/app-init.js + js/dev-banner.js
// consume it.
//
// In production this file is served through Caddy's `templates` module, which
// replaces the {{env "..."}} placeholders with the container's environment
// variables (ANALYTICS_* and DEV from docker/.env, STARTED_AT stamped at
// container start). See docker/Caddyfile + docker/docker-compose.yml.
//
// When served WITHOUT templating (e.g. local dev via `python -m http.server`),
// the placeholders stay literal; the consumers detect the leftover "{{" and
// treat the feature as off, so nothing breaks.
window.__APP_CONFIG__ = {
  url: '{{env "ANALYTICS_URL"}}',
  websiteId: '{{env "ANALYTICS_WEBSITE_ID"}}',
  sri: '{{env "ANALYTICS_SRI"}}',
  dnt: '{{env "ANALYTICS_DNT"}}',
  // "1" turns on the WIP banner; STARTED_AT is the container start time in epoch
  // seconds (stamped by the compose entrypoint) so the banner can say how long
  // ago it was last (re)started. See js/dev-banner.js.
  dev: '{{env "DEV"}}',
  startedAt: '{{env "STARTED_AT"}}',
};
