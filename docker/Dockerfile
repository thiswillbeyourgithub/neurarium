# Hardening customization of the official Caddy image, plus the rate-limit module.
#
# Caddy 2 has no built-in rate limiting, so we compile a custom binary with the
# community module github.com/mholt/caddy-ratelimit (the Caddyfile's `rate_limit`
# directive, a generous per-client flood guard). xcaddy fetches Go modules at
# build time, so `docker compose build` needs network access on the deploy host.
FROM caddy:2-builder-alpine AS builder
RUN xcaddy build --with github.com/mholt/caddy-ratelimit

# The /api Markdown pages (tools/render_api.py): rendered here from the data being
# deployed, so they are never committed. Stdlib only, so a bare python image.
FROM python:3.13-alpine AS api
COPY tools/render_api.py /src/tools/render_api.py
COPY tools/lib/__init__.py /src/tools/lib/__init__.py
COPY tools/lib/page_file.py /src/tools/lib/page_file.py
COPY tools/lib/structure_ids.py /src/tools/lib/structure_ids.py
COPY tools/data_generators/llms_txt.py /src/tools/data_generators/llms_txt.py
COPY tools/data_generators/effect_index.py /src/tools/data_generators/effect_index.py
COPY tools/data_generators/node_id.py /src/tools/data_generators/node_id.py
COPY public/version.js /src/public/version.js
COPY public/data /src/public/data
# Plus the viewer's effect index (data_generators/effect_index.py), the one place the
# effect -> receptors -> drugs join is computed; served at /derived/effects.json.
RUN python -I /src/tools/render_api.py --public /src/public --out /api \
    --effects-out /derived/effects.json

# Runtime: the stock alpine image with our custom binary dropped in over the
# stock one.
#
# The official caddy image runs `setcap cap_net_bind_service=+ep` on the caddy
# binary so it can bind ports 80/443 as a non-root user. We serve on the
# unprivileged port 8359 as UID 1000 with security_opt: no-new-privileges, where
# that *effective* file capability instead makes `execve` fail with
#   exec /usr/bin/caddy: operation not permitted
# We never bind a privileged port, so the capability is unneeded. Our xcaddy-built
# binary carries no such cap, but strip it defensively (a no-op if already absent).
# (Same approach as parakeet_web; libcap is pulled in only transiently.)
FROM caddy:2-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
RUN apk add --no-cache --virtual .build-deps libcap \
    && { setcap -r /usr/sbin/caddy 2>/dev/null || setcap -r /usr/bin/caddy 2>/dev/null || true; } \
    && apk del .build-deps

# Startup wrapper: stamps STARTED_AT and validates ANALYTICS_URL (reachable +
# actually JavaScript) before exec'ing caddy. See entrypoint.sh.
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Served by Caddy at /api/ (see Caddyfile).
COPY --from=api /api /opt/neurarium/api
COPY --from=api /derived /opt/neurarium/derived
