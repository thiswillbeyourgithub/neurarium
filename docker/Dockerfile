# Minimal hardening customization of the official Caddy image.
#
# The official caddy image runs `setcap cap_net_bind_service=+ep` on the caddy
# binary so it can bind ports 80/443 as a non-root user. We serve on the
# unprivileged port 8359 as UID 1000 with security_opt: no-new-privileges, where
# that *effective* file capability instead makes `execve` fail with
#   exec /usr/bin/caddy: operation not permitted
# We never bind a privileged port, so the capability is unneeded: strip it.
# (Same approach as parakeet_web; libcap is pulled in only transiently.)
FROM caddy:2-alpine
RUN apk add --no-cache --virtual .build-deps libcap \
    && { setcap -r /usr/sbin/caddy 2>/dev/null || setcap -r /usr/bin/caddy 2>/dev/null || true; } \
    && apk del .build-deps
