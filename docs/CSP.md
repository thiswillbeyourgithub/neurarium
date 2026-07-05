# Content-Security-Policy

> Reference detail moved out of [`CLAUDE.md`](../CLAUDE.md) to keep that file a terse map. This is the full text for this subsystem.

## Content-Security-Policy

Caddy sends a CSP + `X-Content-Type-Options`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer` on every response (`docker/Caddyfile`).
`default-src 'self'` with `object-src`/`base-uri`/`frame-ancestors`/`form-action`
locked. three.js + eruda are vendored same-origin, so `script-src` needs no CDN.
Relaxations:

- `font-src 'self' data:` — eruda's embedded icon font.
- the umami origin in `script-src` + `connect-src` when configured (entrypoint
  derives `ANALYTICS_ORIGIN`, the Caddyfile interpolates `{$ANALYTICS_ORIGIN:}`).
- `https://*.wikipedia.org` in `connect-src` — info panels fetch the current
  Wikipedia lead (`js/wiki.js`).
- `https://upload.wikimedia.org` in `img-src` — the structure panel hot-links each
  region's illustration. (`img-src` also allows `data:`.)

`script-src`/`style-src` include `'unsafe-inline'` (no-build site: inline importmap,
eruda gate, inline `<style>`). CSP is emitted only by Caddy, not `serve.py`.

> [!IMPORTANT]
> A new external resource (CDN script, remote font, iframe, image host, cross-origin
> fetch) needs the matching CSP directive extended in `docker/Caddyfile`.
