# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

> [!IMPORTANT]
> Keep this file up to date. Whenever a new feature, control, data field, or
> file is added, update the relevant section below in the same change. This file
> is meant to stay an accurate map of the project.

## What this is

A browser-based 3D brain visualizer built on [three.js](https://threejs.org/).
It shows brain regions (cortical lobes, basal ganglia / deep nuclei,
diencephalon, limbic, hindbrain) as procedurally shaped meshes (curl-shaded
cortical lobes, smooth deep nuclei, foliated cerebellum,
swept-tube caudate/brainstem/hippocampus/cingulate/fornix)
and draws arrows for neuron projections between them. Region `group` values
(`lobe`, `basal_ganglia`, `diencephalon`, `limbic`, `hindbrain`) drive the legend
headings + ordering via the `GROUP_LABELS` map in `tools/generate_data.py`, which
is emitted into the data's `meta` record and read by the viewer; adding a new
group means adding it there too or its structures are dropped from the legend.
At explode 0 the regions are positioned and shaped to
lock together into a whole brain (the cortical lobes tile a hemisphere with a
flat medial wall at the longitudinal fissure); the explode slider blows them
radially apart to reveal the deep nuclei. On load the regions start blown out
and animate back together into the whole brain. The view can be rotated/zoomed,
auto-rotated, "blown out" (exploded), and made transparent.

Built with the help of Claude Code.

## Architecture (data vs. rendering, on purpose)

(For a higher-level narrative with diagrams, the module graph, and the boot
sequence, see [`ARCHITECTURE.md`](ARCHITECTURE.md); this section is the detailed
map.)

The anatomy is kept as plain data, separate from the rendering code, so the
project can grow without touching the viewer:

**Project layout.** Everything the browser loads lives under `public/` (the
served site: `index.html`, `app-config.js`, `version.js`, `js/`, `data/`,
`shapes/`), and that directory is the *only* thing exposed to the web: Caddy's
`/srv` and `tools/serve.py` both root at it, so `docker/`, `tools/`, `.git` and
the uncommitted `.env` / `deploy.sh` / `CLAUDE.local.md` are never web-reachable.
Authoring + dev tooling live in `tools/` (`generate_data.py`, `serve.py`,
`shot.py`, `git-hooks/`); deployment config in `docker/`; the README hero shot in
`docs/`. The map below names files by role; their directories are as just listed.

```
tools/generate_data.py  Single source of truth for the anatomy. Defines every
                      region + projection once and emits the two artifacts below.
                      Every translatable display string below is an {en, fr}
                      object (see "Internationalization"); js/data.js localizes
                      them at load. data/brain.jsonl is one JSON object per line.
                      Each line is one of:
                        - a "meta" record (the first line): the presentation maps
                          projection_colors (kind -> arrow colour), kind_labels
                          (kind -> {en,fr} functional-class label) and group_labels
                          (group -> {en,fr} legend heading), so the dataset is self-
                          describing and a port needs no hardcoded palette
                        - a "structure" (region): id, name ({en,fr}, with the
                          hemisphere prefix/suffix), base_name ({en,fr}, hemisphere-
                          stripped, used for the legend row), group, position,
                          color, shape_file, and an optional wikipedia (article
                          URL, shown as a link in the structure info panel)
                        - a "projection": from, to, kind, label ({en,fr}),
                          neurotransmitter ({en,fr}), description ({en,fr}),
                          sources[{citation,url}] (not translated),
                          optional bidirectional, and optional tentative (a
                          speculative pathway: drawn as a dotted arrow in a
                          separate, off-by-default legend section)
                        - a "circuit": id, name ({en,fr}), structures[ids] (a named
                          functional loop; its arrows are derived in the viewer
                          as the projections whose endpoints are both in the set)
shapes/<name>.json    One geometry file per distinct *form* (independent of
                      where it sits / what it connects to). Symmetric left/right
                      pairs share a single right-side file; the left member
                      reflects it (a `mirror` flag on its structure record, see
                      below), so there is no per-side duplication. Three types:
                      "blob" {radii, seed, detail, noise, + optional
                      octaves/ridged/frequency/aniso/clip/clip_planes/carve_tubes}
                      = a gradient-noise-deformed ellipsoid (the optional fields
                      turn the smooth surface into foliated cerebellum; the
                      cortical lobes stay smooth domes and get their "curl" surface
                      from a normal-map shader instead, see js/shapes.js
                      GYRUS_BUMP), `clip` cuts axis-aligned flat faces e.g. the
                      lobes' medial wall, `clip_planes` are the generated
                      bisecting cuts between overlapping neighbours so adjacent
                      regions tile flush like jigsaw pieces instead of inter-
                      penetrating, and `carve_tubes` are swept-tube channels
                      subtracted from a lobe by a `carves` curve (the caudate) so
                      it seats into a notch instead of poking through;
                      "curve" {points, profile, seed, noise, radial/tubular_
                      segments} = a round-capped tapered tube swept along a spline
                      (the C-shaped caudate, the tapering brainstem); "composite"
                      {parts:[...]} = several sub-shapes (each with optional
                      offset/scale/rotate) merged into one mesh, for regions that
                      aren't a single lump (the cerebellum = 2 hemispheres +
                      vermis).
index.html            Page shell: loads three.js (vendored, via import map) and,
                      in debug only, eruda; holds
                      the single bottom-left collapsible "Neurarium" panel
                      (reset/search buttons, the two sliders, auto-rotate, the
                      nested JS-populated legend whose first rows are "show all
                      names" / "hide projections", and a nested About section)
                      plus the in-place search box and
                      the top #banners stack (the WIP banner + error banners).
js/data.js            Fetches brain.jsonl + all shape files, returns a normalized
                      {structures, projections, circuits, byId, meta} object. It
                      reads the meta record's maps and resolves each projection's
                      arrow `color` from its kind (so the viewer reads
                      `projection.color`, never a hardcoded palette); `meta`
                      carries {projectionColors, groupLabels}.
js/shapes.js          Builds a mesh from a shape payload: buildGeometry()
                      dispatches on shape.type to buildBlobGeometry (deformed
                      ellipsoid), buildCurveGeometry (round-capped tapered tube
                      along a spline) or buildCompositeGeometry (merged sub-
                      shapes). A `mirror` flag on the structure reflects the
                      geometry across x (mirrorGeometryX) for the left member of
                      a pair. Self-contained gradient (Perlin) noise +
                      fractal/ridged/domain-warp helpers (fractalNoise). Cortical
                      lobes are smooth domes that get a stylized "curl" pattern as
                      a procedural normal-map bump injected into their material
                      (injectGyrusBump / GYRUS_BUMP: a domain-warped, sine-banded
                      noise field whose iso-loops read as little swirls), so the
                      surface pattern is shading, not triangles. buildBlobGeometry also
                      honours `clip_planes` (the generated inter-region jigsaw
                      cuts) when the `JIGSAW_CLIP.enabled` flag is on, and
                      `carve_tubes` (the caudate hollowing a notch in the lobes it
                      threads) when `CARVE_TUBES.enabled` is on. No JS deps
                      beyond three.js.
js/arrows.js          Builds curved tube+cone arrows for projections; each
                      arrow's colour comes from its `projection.color` (resolved
                      by js/data.js from the data's meta map, single source
                      tools/generate_data.py), not a hardcoded table here. A
                      `projection.tentative` arrow is drawn as a *dotted* tube
                      (a gapped run of short segments merged by a small local
                      mergeIndexedGeometries; no addon) so speculative pathways
                      read as "maybe".
js/labels.js          Floating structure-name labels (three.js CSS2DRenderer):
                      one hidden label per region, shown on hover or all at once.
js/main.js            Scene/camera/renderer/lights/OrbitControls setup, the
                      explode + transparency logic, the auto-play "assemble"
                      intro (createIntroAnimation), auto-rotate, hover raycasting
                      for labels, arrow + structure picking and the info panel
                      (createInfoPanel: a connection view or a structure view
                      with its connection list), the structure+connection search,
                      the legend builder, and the render loop.
app-config.js         Tiny config file (window.__APP_CONFIG__). This committed
                      copy is the LOCAL-DEV fallback: the feature fields are empty,
                      so dev servers keep umami + the DEV banner off. In the
                      container it is NOT served; entrypoint.sh renders an
                      env-filled copy into /gen and Caddy serves that instead (see
                      below). Named generically (not "analytics-*") so content
                      filters / proxies that block "analytics" paths don't 404 it.
                      Carries the umami ANALYTICS_* values, DEV + STARTED_AT (the
                      WIP-banner flag and container start time), and sourceUrl (the
                      "source" link target, from SOURCE_URL, defaulting to the
                      public site).
js/app-init.js        Reads that config and injects the umami tag if configured;
                      no-op otherwise.
js/i18n.js            Internationalization (en / fr). A classic script (like
                      app-config.js) loaded early so the module viewer AND the
                      classic banner scripts can read window.__I18N__. Owns the
                      single UI message catalogue (both languages), detects the
                      language (?lang= param > saved choice > browser locale fr* >
                      en), and on
                      DOMContentLoaded fills the static markup tagged data-i18n /
                      data-i18n-html / data-i18n-attr so English text is not
                      duplicated between the HTML and the catalogue. Exposes
                      t(key,vars) (UI strings) and pick(field) (resolve a
                      translatable {en,fr} *data* field to the current language,
                      used by js/data.js). setLang() saves the choice and reloads
                      (data is resolved at load, see "Internationalization").
js/dev-banner.js      Reads that config and, when DEV=1, shows the top "work in
                      progress / restarted X ago" banner (STARTED_AT drives the
                      "X ago"); no-op otherwise. Lives in the shared #banners
                      stack. See "Dev / WIP banner" below.
js/error-banner.js    Surfaces failures as explicit red, dismissible banners in
                      the #banners stack instead of hiding them in eruda: installs
                      window error + unhandledrejection handlers, exposes a global
                      window.showErrorBanner(msg) for app code, de-dupes repeats
                      into one "(xN)" banner, and republishes the stack height to
                      the --banners-height CSS var so #status stays clear. See
                      "Error banners" below.
version.js            Single source of truth for the app version (a plain
                      `window.__APP_VERSION__` global, no build step). Shown in
                      the panel header (js/main.js) + the WIP banner
                      (js/dev-banner.js). Bump it on a release.
docker/               Deployment: docker-compose.yml (hardened Caddy service),
                      Dockerfile (strips caddy's cap_net_bind_service so exec
                      works under no-new-privileges), Caddyfile (serves /srv on
                      :8359, serves the startup-rendered /gen/app-config.js for
                      /app-config.js, sends Cache-Control: no-store so prod never
                      serves a stale module either, same as tools/serve.py, and
                      sets the security headers incl. a Content-Security-Policy,
                      see "Content-Security-Policy" below),
                      env.example (copy to docker/.env), entrypoint.sh (startup
                      wrapper baked into the image: stamps STARTED_AT, validates
                      ANALYTICS_URL, derives ANALYTICS_ORIGIN for the CSP, and
                      renders /gen/app-config.js from the environment, see below).
tools/shot.py         Screenshot helper (Playwright): serves public/ with
                      tools/serve.py, drives a headless Chromium to load
                      index.html (with view params), and captures the canvas with
                      page.screenshot() to a PNG. Lets a dev/Claude Code see the
                      output. Headless renders WebGL fine once Chromium is given
                      the SwiftShader GL flags (baked in); no $DISPLAY / xdotool /
                      ImageMagick needed. `--headed` opens a real visible window
                      (real GPU) if preferred. Bare `python tools/shot.py` writes
                      docs/screenshot.png (the README hero shot). Needs the
                      playwright package + `playwright install chromium` once (or
                      run via `uv run tools/shot.py`; it carries inline deps).
tools/serve.py        Stdlib static dev server that sends Cache-Control:no-store
                      so the browser never serves a stale ES module (use instead
                      of `python -m http.server` while developing; see Running).
tools/git-hooks/      Repo-tracked git hooks (single source of truth). Currently
                      pre-push, which refuses to push any branch other than
                      main. Activated per-clone with
                      `git config core.hooksPath tools/git-hooks` (see Git hooks).
```

(There are also two uncommitted, environment-specific files not shown above:
`deploy.sh` and `CLAUDE.local.md`; both are gitignored. The latter holds
per-developer setup notes, including the deploy procedure.)

Why a generator instead of hand-written data files: most regions are symmetric
left/right pairs, and the project is expected to get complex. Defining a region
once in `generate_data.py` and mirroring it avoids duplicating anatomical data
across ~20 files. The generated files are committed so the static site can fetch
them directly.

Coordinate convention (arbitrary units, brain centered on origin):
`x` left(-)/right(+), `y` down(-)/up(+), `z` posterior(-)/anterior(+).

## Running

The data files are loaded with `fetch()`, so the page must be served over HTTP
(opening `index.html` via `file://` fails CORS). The served site is `public/`.
From the repo root:

```
python tools/serve.py        # http://localhost:8000/ (recommended for dev)
# or: cd public && python -m http.server 8000
```

(`tools/serve.py` roots at `public/` by default regardless of where you run it;
the bare `http.server` fallback must be started from inside `public/`.)

Prefer `tools/serve.py` while developing: it is the same stdlib server but sends
`Cache-Control: no-store`, so the browser refetches every ES module on each
reload. Plain `http.server` sends no cache headers, and browsers then *heuristic*-
cache the JS modules; that can serve a stale `js/*.js` next to a freshly fetched
one, producing baffling mismatch crashes (e.g. a new `main.js` calling a function
whose old cached signature differs). If you ever see such an error after editing
JS, it is almost always a stale cached module: hard-reload (Ctrl/Cmd+Shift+R) or
switch to `tools/serve.py`.

Debugging: [eruda](https://github.com/liriliri/eruda) provides an on-screen
console (a floating button, bottom-right) usable on desktop and mobile. It is
**gated**: it loads only when `DEV=1` (from `app-config.js`) or the URL carries
`?debug`, so normal production visitors never download or expose it. Append
`?debug` to any URL (e.g. `http://localhost:8000/?debug`) to turn it on in dev.
A small inline gate in `index.html` injects the eruda script when either
condition holds; otherwise the page ships no debug console (runtime errors still
surface to everyone via the red error banners, see "Error banners").

### Screenshots & deep-link view params

`tools/shot.py` renders the page to a PNG so the output can be inspected (this is
how shapes are reviewed/refined, and how the README hero shot is made). It is a
small self-contained Playwright script: it serves the repo with `tools/serve.py`,
drives a headless Chromium, and captures the canvas with `page.screenshot()`:

```
python tools/shot.py                                                  # -> docs/screenshot.png
python tools/shot.py --params "explode=0.5&view=iso" --out /tmp/brain.png
python tools/shot.py --params "only=putamen_R&view=iso" --out /tmp/putamen.png
```

It needs the `playwright` package plus the browser binary
(`playwright install chromium`) once; or run it via `uv run tools/shot.py`, which
auto-installs the inline dependency. Headless WebGL renders correctly because the
script launches Chromium with the SwiftShader GL flags (`--use-gl=angle
--use-angle=swiftshader`); the earlier "headless comes back blank" problem was
just those flags being absent. No `$DISPLAY` / `xdotool` / ImageMagick is needed.

> [!NOTE]
> Pass `--headed` to open a real visible browser window (real GPU) instead of
> headless, e.g. to watch what is being captured. The default headless path is
> the reliable one and needs no display. `--wait` is milliseconds to let the data
> load and a few frames render before the capture (default 6000).

The `--params` string is the URL query parsed by `applyViewParams` in
`js/main.js`, so the same keys also work as deep links in a normal browser:

| key | effect |
| --- | --- |
| `only=id[,id2]` | show only these structure ids (others + all arrows hidden) |
| `view=front\|back\|left\|right\|top\|bottom\|iso` | frame the visible meshes from that angle |
| `explode=0..1` | blow-out amount (also moves the slider) |
| `transparency=0..1` | material opacity |
| `names=all` | show every structure label |
| `autorotate=1` | spin (deep links default auto-rotate **off** so the framed view holds; this forces it on) |
| `ui=0` | hide the control panels + legend (clean shape shots) |

`only`/`view` auto-fit the camera to whatever is visible, so a single structure
fills the frame, handy for reviewing one region's shape at a time.

## Deployment

The site is served by a hardened Caddy container (`docker/docker-compose.yml`):
non-root UID 1000, `cap_drop: ALL`, `no-new-privileges`, read-only rootfs
(writable paths via tmpfs, each `size=`-capped so the RAM-backed mounts can't be
filled to exhaust host memory), CPU + memory + `pids` limits (the last anti
fork-bomb, all under `deploy.resources.limits` so `pids` isn't also set as the
top-level `pids_limit`, which compose rejects as a conflicting double
definition), `mem_swappiness: 0`, and rotated `json-file` logging (so log output
can't fill the host disk). Caddy listens on `:8359`,
published as `127.0.0.1:8359` so a host reverse proxy terminates TLS in front of
it. The image is a thin build on `caddy:2-alpine` (`docker/Dockerfile`) whose
only job is to strip the caddy binary's `cap_net_bind_service` file capability,
which otherwise makes `exec` fail under `no-new-privileges`
(`exec /usr/bin/caddy: operation not permitted`); the `public/` site root (only
the served files, not the rest of the repo) is bind-mounted read-only at `/srv`
at runtime.

The actual deploy procedure (how the tree reaches the server and the restart
commands) is environment-specific and intentionally kept out of this committed
file. See `CLAUDE.local.md` (uncommitted, per-developer setup notes).

## Git hooks

The repo ships its git hooks under `tools/git-hooks/` (tracked, so they are the
single source of truth, not copied into `.git/hooks`). They are activated
**per-clone** by pointing git at that directory once:

```
git config core.hooksPath tools/git-hooks
```

That setting lives in `.git/config` and is *not* committed, so every fresh clone
must run it once (there is no build/install step otherwise). Current hooks:

- `pre-push`: refuses to push any ref other than `main` (other branches, tags,
  and deletes all crash the push). Deployment here does not go through git, so
  `main` is the only ref that should ever leave this machine.

## Internationalization (i18n)

The site is bilingual (English / French), no build step. `js/i18n.js` (a classic
script, loaded early in `index.html`) is the whole mechanism:

- **Two string sources, one pattern.** *UI* strings (panel labels, buttons,
  info-panel headings, banners, ...) live in the message catalogue **inside
  `js/i18n.js`** (one object per language). *Data* strings (region names, pathway
  labels + descriptions, circuit names, legend group headings, neurotransmitters,
  kind labels) live in the data file as `{en, fr}` objects, authored once in
  `tools/generate_data.py` (see "Changing the data") and resolved by `js/data.js`.
- **Generator side (`tools/generate_data.py`).** The anatomy is authored in
  English; a single `FR` table (English string -> French) is the French source,
  and `_t("English")` wraps any display string into `{"en": ..., "fr": FR[...]}`
  when the records are built. A string with no `FR` entry is collected and
  `build_records` **raises listing every missing one**, so the data can never ship
  half-translated. Per-hemisphere names are **composed, not stored**: `_side_name`
  prefixes `Right`/`Left` (English) and suffixes the gender/number-agreed
  `droit/droite/droits/droites` or `gauche/gauches` (French, tuned by an entry's
  optional `fr_gender` of `"m"`/`"f"`/`"mp"`/`"fp"`). Each structure record also
  carries a hemisphere-stripped **`base_name`** `{en,fr}` (the legend groups twins
  by it, so no language-specific prefix parsing). The meta record gains
  **`kind_labels`** (`kind -> {en,fr}` functional-class label) alongside
  `projection_colors`/`group_labels`; `js/data.js` localizes every such field
  (incl. `name`/`base_name`, projection `label`/`description`/`neurotransmitter`,
  circuit `name`, and the `group_labels`/`kind_labels` map values) to plain
  strings at load via `pick`. Source citation text + URLs are not translated.
- **Language pick.** `detectLang()` uses a `?lang=en|fr` query param if present
  (and persists it to `localStorage`, so a deep link *sets the default* for later
  visits too), else a saved choice (`localStorage` `neurarium:lang`), else the
  browser locale (any `fr*` -> French), else English. `window.__I18N__` exposes
  `lang`, `t(key, vars)` (UI lookup with
  `{token}` interpolation, falls back to English then the key), `pick(field)`
  (collapse an `{en,fr}` data field to the current language; a plain string passes
  through), and `setLang(lang)`.
- **Static markup** in `index.html` is *not* duplicated into the catalogue: the
  English text is removed from the HTML and the elements carry `data-i18n="key"`
  (textContent), `data-i18n-html="key"` (innerHTML, for the About paragraphs'
  links) or `data-i18n-attr="attr:key,..."` (attributes like `placeholder` /
  `title`); `i18n.js` fills them from the catalogue at `DOMContentLoaded`.
  Dynamically-built UI (legend, info panel, banners) calls `t()` directly; the
  classic banner scripts read `window.__I18N__` with a key-fallback so an error is
  still surfaced if i18n somehow failed to load.
- **Switching** is a small `EN/FR` control (`#lang-switch`) at the top of the
  panel body (tagged `.collapsible-control`, so it hides with the sliders +
  auto-rotate while a section is open). Clicking the inactive language calls
  `setLang`, which **saves the choice
  and reloads**: `js/data.js` resolves the data language at load, so a reload is
  simpler and more robust than re-rendering the whole scene live. The chosen
  language is also written to `<html lang>`.

> [!IMPORTANT]
> Any new user-visible string must be added to **both** language tables in
> `js/i18n.js` (UI) or authored as an `{en, fr}` object in `generate_data.py`
> (data). Don't hardcode a display string in the viewer or the HTML. Source
> citation text and URLs are intentionally **not** translated.

## Analytics (umami)

Optional, privacy-friendly umami tracking. Because this is a no-build static
site on a read-only rootfs, the config is injected at runtime:

1. Set `ANALYTICS_URL`, `ANALYTICS_WEBSITE_ID` and (optional) `ANALYTICS_SRI` in
   `docker/.env` (see `docker/env.example`). `ANALYTICS_DNT` is umami's
   `data-do-not-track` value (mirrors WebSend's `UMAMI_DNT`): `"true"` (default)
   respects the browser Do Not Track signal, `"false"` tracks all visitors.
2. compose passes them into the container; `docker/entrypoint.sh` renders
   `/gen/app-config.js` from those env vars at container start, and the Caddyfile
   serves that file for `/app-config.js`. (Earlier this was a Caddy `templates`
   block filling `{{env}}` placeholders in the file; that parsed the whole JS as
   a Go template on every request and 500'd on any stray brace marker in the
   file, silently taking both umami and the DEV banner down, so it was replaced
   by the render-once-at-startup approach. The committed `app-config.js` is now
   just the empty local-dev fallback.)
3. `js/app-init.js` reads `window.__APP_CONFIG__` and injects the umami `<script>`
   (with SRI/crossorigin if a hash is given, and an explicit `data-do-not-track`).

   The client-facing file/global names are intentionally generic (`app-config.js`,
   `js/app-init.js`, `__APP_CONFIG__`), not "analytics-*": a path containing
   "analytics" is blocked by many content filters and forward proxies (Squid
   blocklists), which would 404 it before the browser sees it. The `ANALYTICS_*`
   env vars stay as-is since they are server-side and never sent to the client.

Leave `ANALYTICS_URL`/`ANALYTICS_WEBSITE_ID` empty (or run locally without
templating) and analytics is fully disabled, the page works the same.

`ANALYTICS_URL` must be the full URL of the umami tracker *script* (e.g.
`https://umami.example.com/script.js`), not the instance base URL: it is used
verbatim as a `<script src>`, so the instance's HTML homepage would load nothing
and silently record zero events. To make that misconfiguration loud, the
container **validates it at startup** (`docker/entrypoint.sh`): when
`ANALYTICS_URL` is set it must be reachable *and* serve JavaScript (checked via
the response `Content-Type`), otherwise the container refuses to start (crashes)
instead of looking configured while tracking nothing. Empty `ANALYTICS_URL`
skips the check.

## Content-Security-Policy

Caddy sends a `Content-Security-Policy` (plus `X-Content-Type-Options`,
`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`) on every response
(`docker/Caddyfile`). The policy is `default-src 'self'` with `object-src`,
`base-uri`, `frame-ancestors` and `form-action` locked down; the only
third-party origins it allows are:

- `https://cdn.jsdelivr.net` in `script-src`, for the **gated eruda** debug
  console (loaded only on `DEV=1` / `?debug`; see Debugging). Normal visitors
  never fetch it, but the policy is uniform so the origin is allowed.
- the **umami origin** in `script-src` + `connect-src`, when analytics is
  configured. `docker/entrypoint.sh` derives `ANALYTICS_ORIGIN`
  (`scheme://host[:port]`) from `ANALYTICS_URL` and the Caddyfile interpolates it
  as `{$ANALYTICS_ORIGIN:}`; empty (analytics off) adds no extra origin.

`script-src`/`style-src` include `'unsafe-inline'` because this is a no-build
site with an inline `<script type="importmap">`, the inline eruda gate, and an
inline `<style>` block, and there is no bundler to hash/nonce them. That is the
one looseness; it could be tightened to hashes later. three.js is vendored
same-origin (see `public/vendor/three`), so it needs no CDN allowance. The CSP is
only emitted by Caddy in the container, not by `tools/serve.py` in dev.

> [!IMPORTANT]
> If you add a new external resource (another CDN script, a remote font, an
> `<iframe>`, an image host, a cross-origin `fetch`), extend the matching CSP
> directive in `docker/Caddyfile` or the browser will silently block it in prod.

## Dev / WIP banner

Optional "work in progress" banner across the top of the page, for when the
instance is being actively redeployed. Same runtime-injection plumbing as
analytics (no build step):

1. `DEV` in `docker/.env` (default `0`). Set `DEV=1` to enable the banner.
2. The container also needs to know *when it started* so the banner can say
   "restarted X ago". Compose env is static, so the entrypoint
   (`docker/entrypoint.sh`, baked into the image and set as `entrypoint` in
   `docker-compose.yml`) stamps `STARTED_AT=$(date +%s)` (epoch seconds). (The
   same script also validates `ANALYTICS_URL`, see the Analytics section.)
3. The entrypoint then renders `DEV` + `STARTED_AT` (alongside the `ANALYTICS_*`
   values) into `/gen/app-config.js`, which Caddy serves for `/app-config.js`.
4. `js/dev-banner.js` reads `window.__APP_CONFIG__`: when `dev === "1"` it
   reveals `#dev-banner` (an amber bar in the shared `#banners` stack, hidden by
   default via the `hidden` attribute, so `banner.hidden = false` shows it) and
   computes "X minutes/hours/days ago" from `startedAt` client-side (refreshed
   each minute). It does not nudge the rest of the UI itself: the `#banners`
   stack publishes its height as `--banners-height` (see "Error banners"), which
   the `#status` pill offsets against. Any other `DEV` value, or the empty
   local-dev fallback, keeps it hidden, so the banner only ever appears when
   explicitly turned on in a container.
5. **Clicking the banner hides it for the current view only.** The dismissal is
   deliberately *not* persisted (no `sessionStorage`), so a reload brings it back:
   while `DEV=1` the WIP/redeploy warning should keep showing by default rather
   than being silenced for the session by a single click.
6. The banner ends with a **"Source" link** to `cfg.sourceUrl` (from the
   `SOURCE_URL` env var, default the public site; point it at the code repository
   in `docker/.env`). Only an `http(s)` value is rendered, and clicking the link
   navigates instead of dismissing the banner (the dismiss handler ignores clicks
   on an `<a>`). The repo URL is deliberately **not hardcoded** in the committed
   source: it comes from the env var so no specific account/host is baked in.

## Error banners

So a visitor never has to open eruda to find out why something broke, failures
surface as explicit **red, dismissible banners** in the same top `#banners` stack
as the WIP banner (`js/error-banner.js`):

- It installs `window` `error` (capture phase, so failed resource loads count
  too) + `unhandledrejection` handlers that build a banner from the real message
  and, for script errors, the `file:line` it came from, rather than a vague
  "something went wrong".
- It exposes a global **`window.showErrorBanner(message)`** so app code can
  surface its own explicit errors the same way. `js/main.js` uses it for the
  brain-data load failure (replacing the old red `#status` pill there).
- Multiple errors **stack** as separate banners (newest below the dev banner /
  earlier errors); each has a **×** button to dismiss it. Identical messages are
  **de-duplicated** into one banner with an `(×N)` repeat counter (so a fault
  firing every animation frame can't flood the screen), and there is a hard cap
  (`MAX_BANNERS`) on distinct banners.
- A `ResizeObserver` on `#banners` republishes the stack height to the
  `--banners-height` CSS variable, which the `#status` pill's `top` offsets
  against, so the pill always sits below whatever is stacked (dev banner +
  errors), with no per-banner body class.

## Controls

- **Panel layout**: everything except the bottom-right info panel
  lives in one collapsible **"Neurarium" panel at the bottom-left** (`#controls`
  in `index.html`, its header `#controls-toggle` collapses the whole body). From
  the top it holds: the **reset + search** icon buttons (a `.toolbar-row`), then
  the **Separate** and **Transparency** sliders, then **Auto-rotate**, then the
  nested collapsed **Legend** (`#legend`) whose first rows are the **Show all
  names** and **Hide projections** buttons, then the nested collapsed **About**
  (`#about`) section. Searching swaps the search box in place of the panel's
  normal contents (`#controls-main` hidden, `#search` shown) rather than opening
  a popup; the reset/search buttons stay visible so the magnifier toggles back.
  The panel / legend / about collapse headers share one `wireCollapse` helper in
  `js/main.js`. **Legend and About are an accordion**: opening one closes the
  other (only one open at a time), and while either is open every control above
  it (the `#lang-switch`, the `.toolbar-row`, the two sliders and the Auto-rotate
  checkbox, all tagged `.collapsible-control`) is hidden via the
  `#controls.section-open` class so the open section's content doesn't push the
  panel tall; only the two section headers stay visible. `wireCollapse` takes an
  `onToggle(open)` callback
  and `setSection()` sets a section's state programmatically; `syncSectionLayout()`
  toggles `section-open`. A section can only be opened while the controls are
  visible (i.e. not searching), so this never hides the toolbar mid-search.
- **About** (`#about`, collapsed by default): a short blurb (what Neurarium is,
  that it's a WIP, made by Olivier Cornelis + Claude) plus a **Source code** link
  whose href is set from `cfg.sourceUrl` by `js/main.js` (the row is removed if
  that isn't a valid `http(s)` URL). See "Dev / WIP banner" for `sourceUrl`.
- **Auto-rotate** checkbox: spins the camera around the brain (OrbitControls
  `autoRotate`). **On by default** (a slow turn on load); it switches itself off
  (and unticks the box) the moment the user picks content, i.e. any pick routed
  through the selection controller (a structure/arrow click-tap-or-search, a
  legend isolate, or a circuit), so what you clicked holds still. Clearing the
  selection does not re-enable it. Wired via `selection.onPick(stopAutoRotate)`
  in `js/main.js`. Deep links / screenshots get it forced **off** by
  `applyViewParams` unless `?autorotate=1` is passed, so a framed view holds.
- **Separate** slider (0..1, labelled "Separate" in the UI; the explode/`?explode`
  terminology lives on internally): pushes each region radially outward from
  the brain center to reveal deep structures. Tuning constant:
  `EXPLODE_STRENGTH` in `js/main.js`.
- **Intro animation**: on a plain page load the regions start fully blown out
  and glide back together into the assembled whole over a swift, eased motion
  (`createIntroAnimation` in `js/main.js`, advanced once per frame in the render
  loop; duration `INTRO_DURATION_MS`, easeInOutCubic). It moves the explode
  slider in sync, is cancelled the moment the user grabs that slider, and is
  skipped when `?explode=` is pinned (deep links / headless screenshots) so the
  requested static amount is honored.
- **Transparency** slider: the value is the material opacity (left = more
  transparent); depth-writing is disabled while translucent so overlapping
  regions blend. Opacity is owned by the selection controller
  (`createSelection` in `js/main.js`), not a standalone helper, so the slider
  value and the isolate-mode dimming (below) compose into one final per-mesh
  opacity.
- **Selection / halo + isolate** (`createSelection` in `js/main.js`): the single
  source of truth for which structures/arrows are highlighted/focused.
  - Picking a structure in the 3D view (click/tap or a structure
    search result) gives it a soft glowing **halo** (a back-side additive shell
    child, `mesh.userData.halo`); this is a lightweight highlight only, no
    dimming. (A **double-click** instead isolates the structure, like its legend
    row, see below.) Picking an **arrow** (click/tap or a connection search result) halos
    it too (a fatter additive tube along its arc, `ProjectionArrow.setHalo`); the
    structure halo and arrow halo are mutually exclusive.
  - Clicking a **structure row in the legend** toggles that structure (both
    hemispheres) into the **isolate** set; clicking a **category heading** toggles
    every structure under it at once. While the set is non-empty the scene focuses
    on it: every other structure drops to a faint opacity (`DIM`), arrows that
    don't touch an isolated structure fade with them (`ProjectionArrow.
    setOpacity`), the isolated structures keep full (slider) opacity + halo, and
    the legend greys its non-isolated rows/headings (`.dimmed`, isolated ones get
    `.selected`). Legend selection is additive (click more rows to add).
  - The **Circuits** legend section lists curated functional loops (from the
    `circuit` records). Clicking one isolates *exactly* that circuit: its
    structures + the projections between them stay opaque, everything else fades
    (`selection.setCircuit`, which pins an explicit arrow set instead of the
    "touching" rule). Clicking the active circuit again clears it.
  - The **Projections** legend section lists one row **per neurotransmitter**
    (the molecule, e.g. `Glutamate (excitatory)`, coloured by its arrow `kind`
    and labelled with that functional kind in parens). Rows are per-transmitter,
    not per-kind, so when a kind later carries more than one transmitter they
    split into their own rows automatically; with today's 1:1 data each kind has
    exactly one. Each row is clickable: clicking one isolates *only* that
    neurotransmitter via the same `setCircuit` machinery (it pins every arrow
    using that transmitter plus the structures they connect, so just those
    pathways + their endpoints stay opaque and everything else fades). Unlike a
    circuit, such a focus dims *every* structure, so its structure/heading rows
    grey out rather than lighting up; only the neurotransmitter row lights.
    Clicking the active one again clears it. The per-neurotransmitter rows are
    built from the **non-tentative** projections only (the speculative ones live
    in their own section below).
  - The **Hypothetical pathways** legend section is separate and **off by
    default**: a single "Show speculative (N)" toggle reveals/hides every
    `tentative` projection's (dotted) arrow at once. They are deliberately kept
    out of the per-neurotransmitter rows so a speculative link never reads as an
    established one. Visibility composes with the global **Hide projections**
    button via `createProjectionVisibility` in `js/main.js`: an arrow shows only
    when projections aren't globally hidden *and* it is established or (when
    tentative) its section is toggled on (global-hide wins; re-showing restores
    the tentative arrows only if their section is on).
  - The **reset** button and a **double-click on empty space** fully clear it
    (halos + isolate + circuit), restoring default opacity. Framing a connection
    or arrow just swaps the halo, leaving any isolate set intact.
- **Structure names**: hovering a region with the mouse (or tapping it on a
  touch screen) shows its name as a floating label; tapping empty space clears
  it. Raycast in `js/main.js` -> `js/labels.js`. The **Show all names** button
  (the legend's first row) forces every label on at once. Labels are boxless:
  white glyphs outlined in the structure's own color (`--label-color`) plus a
  black halo, so they stay legible over any region and overlapping names don't
  hide behind opaque boxes.
- **Legend**: nested inside the bottom-left panel, collapsed by default; click
  its header to expand. It starts with the **action buttons** (a `#legend-actions`
  container kept first across rebuilds by `buildLegend`, which preserves that
  node): **Show all names** and **Hide projections** (off by default; toggles
  every arrow's visibility at once via `arrow.setVisible`, and refreshes labels
  so the connection labels follow). The rest is generated from the data (see
  below). Each structure row is clickable to isolate/focus that region, and each
  **neurotransmitter row** is clickable to isolate that transmitter's pathways
  (see Selection above).
- **Touch / mouse**: one finger or left-drag rotates; two-finger pinch (or
  scroll wheel) zooms; two-finger drag pans. Handled by OrbitControls.
  **Shift + wheel** drives the **Separate** slider instead of zooming: a
  capture-phase `window` wheel listener in `js/main.js` runs before
  OrbitControls, and on `shiftKey` swallows the event (preventDefault +
  stopPropagation) and nudges the slider (dispatching its `input` event so the
  intro-cancel + re-aim fire). Plain wheel falls through to zoom.
- **Reset + search** (the icon-button row at the top of the panel, just above the
  sliders): a **reset** button (crosshair icon) recenters the camera on the
  middle of the brain and re-frames the whole thing (useful after panning slides
  it off-center), and a **search** button (magnifier icon) swaps a search box in
  place of the panel body (not a popup) that filters **both structures (by name)
  and connections (by pathway label)**. Picking a structure centers on it,
  shows its label, and opens its structure panel (below);
  picking a connection frames its two endpoints and opens the connection panel.
  Connection results carry a hemisphere tag (`R` / `L` / `L↔R`) so the mirrored
  twins stay distinct (`connectionSideTag` in `js/main.js`). **Ctrl/Cmd+F** is a
  shortcut for the same search: a `window` keydown listener intercepts it (so the
  browser's native page-find, useless on a canvas + data app, never opens),
  expands the panel if it was collapsed (the search box lives inside the panel
  body) and opens search focused on its input; pressing it again while open just
  refocuses + selects the text. **Escape** closes search.
- **Info panel** (bottom-right, `createInfoPanel` in `js/main.js`): one panel
  that shows either a *connection* or a *structure*.
  - **Clicking/tapping an arrow** (or picking a connection in search) shows the
    **connection** view: the pathway label, its route (`from → to`, `↔` for a
    bidirectional/commissural link), kind + neurotransmitter, a one-line
    description, and its sources (a verified http(s) url renders as a link, a
    `"TODO"` url as plain text). Built from the projection's metadata. Arrow
    picking (`pickArrowAt`) takes priority over the region behind it.
  - **Clicking/tapping a structure** (or a structure search
    result) shows the **structure** view (`showStructure`): its name, its group
    heading (from `data.meta.groupLabels`), a **Wikipedia link** when the
    structure record carries a `wikipedia` url (rendered only for an http(s)
    value), and the list of pathways touching it. Each connection row
    shows a kind-coloured swatch, a direction glyph (`→` it projects out, `←` it
    receives, `↔` reciprocal) and the other endpoint; **clicking a row jumps to
    that pathway** (frames the endpoints, halos the arrow, swaps in the
    connection view) via the panel's `onConnection` hook, wired in `js/main.js`
    to the same action as a connection search result. A structure with no mapped
    pathways shows "No mapped connections yet."
  - A click/tap that **misses** every arrow and structure (empty space) closes
    the panel.
- **Double-click**: on a structure **isolates/focuses** it (both hemispheres),
  exactly like clicking its legend row (`selection.toggleIsolate`, see Selection
  above); on empty space recenters the whole brain (same as the reset button).
- All camera framing above (reset, search) goes through one smooth
  tween, `createCameraFocus` in `js/main.js`: it moves the orbit pivot and
  camera distance but keeps the current view direction, is advanced once per
  frame in the render loop, and is cancelled the moment the user grabs the
  controls so a drag always wins.
- After focusing a single structure (a structure search), moving
  the **blow-out** slider keeps that structure centered: `createCameraFocus`
  remembers it (`focused`) and `reaimFocused()` (called from the explode handler)
  re-points the orbit pivot at its new exploded position. Only the pivot moves,
  so the camera *rotates in place* to track it (a reorientation, not a
  translation), preserving the distance + angle you set. Framing a connection or
  the whole brain clears the tracked structure.

## Changing the data

1. Edit the `PAIRED`, `MIDLINE`, or `PROJECTIONS` lists in `generate_data.py`.
   - Paired entries are auto-mirrored to both hemispheres (`_R` / `_L`). Define
     them on the **right** side (x > 0); the generator emits one shared
     right-side shape file and the `_L` member references it with `mirror:true`,
     so the viewer reflects the geometry across x (a *true* mirror, not a copy).
   - A region is a gradient-noise-deformed ellipsoid by default
     (`radii`/`seed`/`detail`/`noise`). Optional surface knobs shape the
     character of that noise (consumed by `buildBlobGeometry` in `js/shapes.js`):
     - `octaves` (default 1): fBm layers; >1 adds finer wrinkles on the broad
       form. Cortex uses ~2 with a small `noise` so the lobes stay smooth broad
       domes (the surface *curls* are a normal map, see below, not geometry). The
       ridged path is a ridged-multifractal: each finer octave is gated by the
       coarser one's ridge strength, so troughs stay smooth instead of filling
       with creases.
     - `ridged` (default False): fold the noise into sharp creases along its
       zero-set. This is what turns lumps into folia (the cerebellum). Needs
       higher `detail` (6) and lower `noise` than a smooth blob, and a `frequency`
       that sets how many folds. (The cortical lobes no longer use it: they are
       smooth domes carrying a curl normal-map instead.)
     - `frequency` (default 2.4): noise lattice frequency; higher = smaller,
       more numerous folds.
     - `aniso` ([ax,ay,az], default [1,1,1]): per-axis frequency skew. Equal =
       isotropic meandering gyri; a big single-axis value stacks near-parallel
       bands (the cerebellum's folia use a strong y skew).
     Smooth deep nuclei just use `detail` 5 + a small `noise` (~0.05) and none of
     the above.
     - `clip` ({x/y/z min/max}): cut axis-aligned flat faces. Rarely set by hand;
       setting `medial=True` on a lobe makes the generator derive the right medial
       clip from its side so the hemispheres meet at the midline (see below).
     - `clip_planes` (auto, never authored): the generator computes a bisecting
       cut plane between each blob and every overlapping *same-group* neighbour
       (`_bisecting_clip_planes` in `generate_data.py`) and clamps vertices past
       it onto it (`buildBlobGeometry`), so overlapping regions grow flat mating
       faces and tile flush like jigsaw pieces (the lobes, and the deep nuclei
       among themselves) instead of one colour poking through another. Adjacency
       is derived from the geometry (a plane appears only where two bodies' reach
       overlaps), the seam is split by each body's reach so the larger keeps more,
       and only blobs take part (curves/composites are skipped). It is built once
       on the right side and mirrored with the rest of the geometry. The
       `JIGSAW_CLIP.enabled` flag in `js/shapes.js` is the A/B switch: turn it off
       to ignore the planes (regions overlap as before) without regenerating; the
       medial wall is independent and always applied.
     - `carve_tubes` (auto, never authored): a curve flagged `carves=True` (the
       caudate) hollows a swept-tube *channel* out of every lobe its spine threads,
       so it sits in a clean notch ("partly exposed", a jigsaw piece set into the
       seam) instead of the cortex poking through it. The generator
       (`_tube_carve` in `generate_data.py`) emits, on each threaded lobe, the
       carver's spine points + per-station channel radius (its `profile` inflated
       by noise + `LOBE_CARVE_GAP`) in that lobe's local frame;
       `buildBlobGeometry` pushes any lobe vertex inside the tube out onto the
       tube surface. Adjacency is geometry-derived (a spine point reaching inside
       the lobe), only `group=="lobe"` blobs are carved (a nucleus never carves a
       lobe), and like the planes it is computed once on the right side and
       mirrored. The `CARVE_TUBES.enabled` flag in `js/shapes.js` is the A/B
       switch. (The caudate is also nudged up so its head emerges through the
       fronto-parietal seam; per-explode it pulls back out of the notch, which is
       expected.)
     - The cortical surface pattern is *not* geometry: every `group=="lobe"`
       structure gets a procedural "curl" bump injected into its material
       (`injectGyrusBump` / the `GYRUS_BUMP` knobs in `js/shapes.js`). The height
       field is a domain-warped, sine-banded noise field whose iso-loops close
       into little swirls; its gradient perturbs the per-fragment normal so the
       lighting shows soft curls with no extra triangles or faceting. Tune via
       `GYRUS_BUMP`: `freq` (curl size), `warp` (how swirly), `bands` (line
       packing), `scale` (relief), `octaves` (low = clean loops); `enabled:false`
       skips the shader entirely, `scale:0` keeps it compiled but flat. It lives
       in JS, not the data.
   - Give a region a `shape=dict(type="curve", ...)` for a round-capped tapered
     tube instead of an ellipsoid (the caudate, the brainstem): `points` is the
     spine head->tail, `profile` the radius sampled along it (caps close each
     end). A paired `curve` may now be asymmetric across x (e.g. an off-midline
     spine): the `_L` member is a true reflection of the right-side geometry, so
     it flips correctly. Midline curves like the brainstem are emitted once and
     never mirrored. A curve may also carry `carves=True` to make it hollow a
     notch in the lobes it threads (see `carve_tubes` above; only the caudate uses
     it).
   - Give a region a `shape=dict(type="composite", parts=[...])` to merge several
     sub-shapes into one mesh; each part is a shape payload (usually a blob) with
     optional `offset`/`scale`/`rotate`. Used for the cerebellum (two foliated
     hemispheres + a central vermis). A paired composite is mirrored as a whole
     for the `_L` side, so its parts may sit asymmetrically across x.
   - Layout / "lock into place": regions are positioned (the `pos` field) so that
     at explode 0 they assemble into a whole brain, and the explode slider pushes
     each radially outward from the origin (`EXPLODE_STRENGTH` in `js/main.js`).
     The cortical lobes are sized to *overlap* their neighbors (so their union is
     one continuous hemisphere, not separate balls) and flagged `medial` so a
     flat wall at `MIDLINE_GAP` forms the longitudinal fissure; the temporal is
     the exception (lateral, below the Sylvian fissure: no medial wall, just a
     flat `ymax` top). Deep nuclei sit small and central so they hide inside the
     cortex at 0 and are revealed by exploding. When moving a lobe, re-render the
     assembled hemisphere (`only=frontal_R,parietal_R,temporal_R,occipital_R&
     explode=0&view=right|left|top`) to check the seams and the medial wall.
   - To give a region a **Wikipedia link**, add its `base` id + article URL to the
     `WIKIPEDIA` registry near the top of `generate_data.py` (a small map keyed by
     base id, like `SOURCES`, so both hemispheres of a pair share the one article
     written once). The generator attaches the URL to each structure record
     (`_structure_record`) and the viewer shows it as a link in the structure info
     panel; a base absent from the map just gets no link, and a key that is not a
     known structure base raises in `build_records` (typo guard).
   - Projection `from`/`to` reference structure ids (e.g. `putamen_R`). The arrow
     points `from` -> `to` (a cone at the target end).
   - A projection carries metadata so the viewer can explain it: `label` (short
     pathway name, also what the search box matches on), `neurotransmitter` (the
     specific molecule), `description` (one-line summary), and `sources` (a list
     of `SOURCES` keys). Keep the `label` unique-ish and human-readable: clicking
     an arrow or picking it in the search opens an info panel built from these
     fields, so every connection must have a name.
   - `sources`: cite shared references by short key from the `SOURCES` registry at
     the top of `generate_data.py` (so a citation common to several pathways is
     written once); the generator expands each key to a full `{citation, url}`
     object in the emitted data (`_expand_sources`, raises on an unknown key). New
     references go in `SOURCES`; leave `url` as the literal `"TODO"` until a real
     link is verified (the panel renders an http(s) url as a link, `"TODO"` as
     plain text). **There are currently TODO urls on every source** awaiting real
     DOIs/links.
   - `bidirectional: True` draws a cone at *both* ends (reciprocal / commissural
     pathways). Use it with `symmetric: False` and explicit `_L`/`_R` endpoints
     for the commissures (corpus callosum, anterior commissure) so the single
     cross-midline connection is not mirrored into a duplicate.
   - `tentative: True` marks a **speculative / less-certain** pathway. It is
     carried through to the emitted record; the viewer draws such arrows as a
     *dotted* tube and lists them in a separate, off-by-default "Hypothetical
     pathways" legend section (not in the per-neurotransmitter rows), so they read
     as "maybe" and never masquerade as established connections.
   - Projections are **bilateral by default**: define a symmetric pathway once
     on the right and the generator emits a hemisphere-flipped twin (`_R` <->
     `_L` on both endpoints; midline endpoints stay put). Set
     `"symmetric": False` on an entry to keep a genuinely one-sided pathway from
     being mirrored. The flag is a generator hint and is stripped from the data.
   - Projection `kind` must be a key of `PROJECTION_COLORS` in
     `tools/generate_data.py` (`excitatory`, `inhibitory`, `dopaminergic`,
     `cholinergic`, `neuroendocrine`); add
     new kinds there (the generator raises if a projection uses an unmapped kind)
     + in this doc if needed. The map is emitted into the data's `meta` record and
     each projection gets a resolved `color` at load, so the viewer never
     hardcodes the palette. `kind` drives the arrow *color*; `neurotransmitter` is
     the finer label shown in the info panel.
   - To add a named **circuit**, append to the `CIRCUITS` list: `id`, `name`, and
     `structures` as **base** ids (no `_R`/`_L`). The generator expands each base
     to whatever was emitted (both hemispheres, or the bare id for a midline form)
     and raises on a typo; the circuit's arrows are *not* listed (the viewer takes
     every projection whose endpoints are both in the set), so a circuit never
     duplicates the pathway list. It shows up in the legend's Circuits section.
   - **Translations.** Every display string (a region `name`, a projection
     `label`/`description`/`neurotransmitter`, a circuit `name`, a group/kind
     label) is wrapped with `_t()` at build time, which looks the English text up
     in the `FR` table (English -> French) near the top of the file. Add the
     French there for any new/edited string: the generator **raises listing every
     untranslated string** if you forget, so it can't ship half-translated. For a
     paired structure whose French name is feminine or plural, set `fr_gender`
     (`"f"`/`"mp"`/`"fp"`; default `"m"`) so the composed "droit/droite/..." side
     suffix agrees. See "Internationalization".
2. Run `python tools/generate_data.py` to regenerate `public/data/` and
   `public/shapes/`.
3. Commit the generator change and the regenerated artifacts together.

The legend (region colors and the per-neurotransmitter projection rows) is
generated at runtime from the data, so it updates automatically; no separate
legend edit is needed.

## Versioning

Lightweight, no-build versioning suited to this static site:

- The version is a single string in `version.js` (`window.__APP_VERSION__`), the
  one place to change it. `js/main.js` shows it in the panel header (`v0.1.0`)
  and `js/dev-banner.js` appends it to the WIP banner; both just read the global,
  so there is no duplication.
- Follow [semver](https://semver.org/) (MAJOR.MINOR.PATCH). To release, bump
  `version.js`.
- It is intentionally *not* derived from git (the site is deployed as plain
  files, not from a repo checkout, so a baked-in string is what actually reaches
  the browser).

## Conventions

- No JS build step or package manager: three.js is vendored same-origin under
  `public/vendor/three` and loaded via an import map in `index.html`. Keep the
  `three` and `three/addons/` entries in that import map pointing at the vendored
  files, and bump the vendored copy as a unit.
- `generate_data.py` is intentionally stdlib-only so it runs offline with a bare
  `python` interpreter.
- Avoid duplicating the anatomy *and its presentation maps*:
  positions/colors/shape params, the projection `kind`->colour map and the
  `group`->legend-heading map all live only in `generate_data.py`; the latter two
  are emitted into the data's `meta` record and read by the viewer, so there is
  no second copy in JS.
