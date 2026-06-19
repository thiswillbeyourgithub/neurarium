// Runtime app configuration: the optional umami metrics tag plus the optional
// "work in progress" dev banner.
//
// Named generically on purpose: a file/path containing "analytics" (or "track",
// "stats", ...) gets blocked by many content filters and forward proxies (e.g.
// Squid blocklists), which would 404 it before it reaches the browser. Keeping
// the URL neutral lets the request through; js/app-init.js + js/dev-banner.js
// consume it.
//
// This committed copy is the LOCAL-DEV fallback. tools/serve.py / `python -m
// http.server` serve it as-is, where there is no container environment to
// inject, so the feature fields are empty and the umami tag + DEV banner stay
// off. (`sourceUrl` is not a feature toggle: it defaults to the public site so a
// "source"/"about" link always has somewhere to point; the container overrides
// it from the SOURCE_URL env var, e.g. to the code repository.)
//
// In the CONTAINER this file is NOT served. docker/entrypoint.sh renders an
// equivalent file from the environment (ANALYTICS_* and DEV from docker/.env,
// STARTED_AT stamped at start) into a writable tmpfs at container start, and
// docker/Caddyfile serves THAT for /app-config.js. Rendering it once at startup
// (rather than templating on every request) means Caddy never parses this JS as
// a template, so the file can contain anything (including brace markers) without
// breaking. Keep the keys below in sync with the heredoc in
// docker/entrypoint.sh.
window.__APP_CONFIG__ = {
  url: '',
  websiteId: '',
  sri: '',
  dnt: '',
  dev: '',
  startedAt: '',
  sourceUrl: 'https://neurarium.olicorne.org',
};
