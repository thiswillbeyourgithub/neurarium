# Deployment & git hooks

> Reference detail moved out of [`CLAUDE.md`](../CLAUDE.md) to keep that file a terse map. This is the full text for this subsystem.

## Deployment

A hardened Caddy container (`docker/docker-compose.yml`): non-root UID 1000,
`cap_drop: ALL`, `no-new-privileges`, read-only rootfs (writable paths via
`size=`-capped tmpfs), CPU + memory + `pids` limits (all under
`deploy.resources.limits` so `pids` isn't double-defined, which compose rejects),
`mem_swappiness: 0`, rotated `json-file` logging. Listens `:8359`, published
`127.0.0.1:8359` so a host reverse proxy terminates TLS in front. The image
(`docker/Dockerfile`) is a two-stage build: a `caddy:2-builder-alpine` stage
`xcaddy build`s a custom binary with the `github.com/mholt/caddy-ratelimit` module
(Caddy has no built-in rate limiting, so `docker compose build` needs network on
the deploy host), dropped into a `caddy:2-alpine` runtime stage that also strips
the binary's `cap_net_bind_service` (else `exec` fails under `no-new-privileges`);
`public/` is bind-mounted read-only at `/srv`. The `Caddyfile` adds a generous
per-client `rate_limit` flood guard keyed on `{client_ip}`, which relies on the
host reverse proxy forwarding `X-Forwarded-For` (trusted via `trusted_proxies`); if
it does not, rate-limit at the front proxy instead. The actual deploy procedure is
in `CLAUDE.local.md`.

## Git hooks

Shipped under `tools/git-hooks/` (tracked = single source of truth), activated
per-clone once: `git config core.hooksPath tools/git-hooks` (not committed; every
fresh clone runs it). Current:

- `pre-push`: refuses any ref but `main`. On `main`, prompts on the terminal
  (`y/N`, via `/dev/tty`) to run `tools/check_data.py`; a check that reports
  **errors** aborts the push (warnings pass). A non-interactive push skips the prompt.
