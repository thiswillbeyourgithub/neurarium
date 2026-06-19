#!/bin/sh
# Container entrypoint for the Neurarium static site. Three jobs before handing
# off to Caddy:
#
#   1. Stamp the container start time into STARTED_AT (epoch seconds) so the
#      optional DEV banner can show "restarted X ago" (js/dev-banner.js).
#      Compose env is static, so we stamp it here at run time.
#
#   2. Fail fast on a half-configured ANALYTICS_URL. If it is set it MUST be
#      reachable AND actually serve JavaScript (the umami tracker, e.g.
#      .../script.js). A common mistake is pointing it at the umami *instance*
#      base URL: that is reachable but returns an HTML page, so the <script>
#      injected by js/app-init.js loads no tracker and records zero events while
#      looking configured. We refuse to start rather than silently track
#      nothing. (Empty ANALYTICS_URL = analytics disabled = no check.)
#
#   3. Render the runtime app config (window.__APP_CONFIG__) from the environment
#      into /gen/app-config.js, which Caddy serves for /app-config.js (see
#      docker/Caddyfile). The project root is mounted read-only, so we write to
#      /gen (a writable tmpfs). Doing the substitution here, once, instead of via
#      Caddy's templates module on every request means Caddy never parses the JS
#      as a Go template and so cannot 500 on a stray brace marker in the file.
#
# Note this couples startup to the umami instance being up at that moment; that
# is intentional (fail loud on misconfig). Relax the check below if you ever
# want the site to start regardless.

set -eu

export STARTED_AT="$(date +%s)"

if [ -n "${ANALYTICS_URL:-}" ]; then
  echo "entrypoint: validating ANALYTICS_URL=$ANALYTICS_URL"

  # busybox wget: -S dumps the response headers to stderr, the body is
  # discarded. A non-zero exit means unreachable or an HTTP error (DNS failure,
  # connection refused, 4xx, 5xx) -> crash.
  if ! headers="$(wget -S -O /dev/null "$ANALYTICS_URL" 2>&1)"; then
    echo "entrypoint: FATAL ANALYTICS_URL is not reachable:" >&2
    echo "$headers" >&2
    exit 1
  fi

  # It resolved, but it must be JavaScript, not the instance's HTML page. Take
  # the LAST Content-Type (the final response after any redirects). This is the
  # check that catches the "base URL instead of script.js" mistake.
  ctype="$(printf '%s\n' "$headers" | grep -i 'content-type:' | tail -n1 | tr 'A-Z' 'a-z')"
  case "$ctype" in
    *javascript*)
      echo "entrypoint: ANALYTICS_URL OK (reachable, serves JavaScript)"
      ;;
    *)
      echo "entrypoint: FATAL ANALYTICS_URL did not return JavaScript." >&2
      echo "entrypoint: point it at the umami tracker script (e.g. .../script.js)," >&2
      echo "entrypoint: not the instance base URL." >&2
      if [ -n "$ctype" ]; then
        echo "entrypoint: got -> $ctype" >&2
      else
        echo "entrypoint: got -> (no Content-Type header)" >&2
      fi
      exit 1
      ;;
  esac
fi

# Render the app config from the environment into the /gen tmpfs. An unset var
# becomes an empty string (features stay off); the consumers (js/app-init.js,
# js/dev-banner.js) treat empty values as "disabled". Keep these keys in sync
# with the local-dev fallback in app-config.js.
cat > /gen/app-config.js <<CONFIG
// Generated from the container environment by docker/entrypoint.sh at startup.
window.__APP_CONFIG__ = {
  url: '${ANALYTICS_URL:-}',
  websiteId: '${ANALYTICS_WEBSITE_ID:-}',
  sri: '${ANALYTICS_SRI:-}',
  dnt: '${ANALYTICS_DNT:-}',
  dev: '${DEV:-}',
  startedAt: '${STARTED_AT:-}',
};
CONFIG
echo "entrypoint: rendered /gen/app-config.js (dev='${DEV:-}')"

exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
