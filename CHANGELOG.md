# Changelog

All notable changes to this project are recorded here. The project follows
[semantic versioning](https://semver.org/) (MAJOR.MINOR.PATCH); the current
version is the single source of truth in [`version.js`](version.js) and is shown
in the app's panel header. Bump `version.js` and add an entry here in the same
change.

Built with the help of Claude Code.

## 0.5.0

- Fixed `app-config.js` returning HTTP 500, which silently disabled BOTH umami
  analytics and the DEV "work in progress" banner. Caddy's `templates` module
  parsed the whole served file as one Go template, and literal template-action
  markers in the file's own explanatory comments (a `"{{`) broke the parse. The
  runtime config is no longer templated per request: `docker/entrypoint.sh` now
  renders `/gen/app-config.js` from the environment once at container start and
  Caddy serves that file, so it is never parsed as a template and cannot 500 on
  its contents. The committed `app-config.js` is now the empty local-dev
  fallback. Touches `docker/Caddyfile`, `docker/entrypoint.sh` and
  `docker/docker-compose.yml` (new `/gen` tmpfs).

## 0.4.0

- Rewrote the screenshot helper (`tools/shot.py`) as a small self-contained
  Playwright script: it serves the repo with `tools/serve.py`, drives a headless
  Chromium, and captures the canvas with `page.screenshot()`. Headless WebGL now
  renders correctly because Chromium is launched with the SwiftShader GL flags
  (the old "headless comes back blank" issue was just those flags missing), so
  the previous `--headed` X11 path (`$DISPLAY` + `xdotool` + ImageMagick) and the
  manual browser autodetection are gone. Bare `python tools/shot.py` now writes
  `docs/screenshot.png` (the README hero shot); `--headed` still opens a real
  window if wanted. The capture is auto-cropped to the rendered content (with a
  small margin) so the subject fills the frame; pass `--no-crop` to keep the full
  viewport. Regenerated `docs/screenshot.png` with it.
- Hid the native scrollbar on the control / legend / search / info panels (they
  still scroll via wheel / touch / drag); the chunky bar looked out of place over
  the dark glass UI.

## 0.3.0

- Validate `ANALYTICS_URL` at container startup (`docker/entrypoint.sh`): when
  it is set it must be reachable and actually serve JavaScript (the umami
  tracker script), otherwise the container refuses to start. This makes a
  half-configured value (e.g. the umami instance base URL instead of its
  `script.js`) fail loudly instead of silently recording zero events. The
  start-time stamping for the DEV banner moved into the same entrypoint script.

## 0.2.0

- Renamed the project to **Neurarium** (previously "BrainWebViz" / "Brain
  Visualizer"): the page title, control-panel header, README, docs, Docker
  service/image/container names, and the screenshot tooling were all updated.

## 0.1.0

Initial versioned release of the browser-based 3D brain visualizer:

- Procedurally shaped brain regions (gyrified cortex, smooth deep nuclei,
  foliated cerebellum, swept-tube structures) that assemble into a whole brain
  and blow apart with the explode slider.
- Curved arrows for neuron projections, colored by kind, with an info panel and
  curated functional circuits.
- Selection: halo highlighting plus legend-driven isolate/focus and circuit
  isolation.
- Structure + connection search and floating name labels.
- Single consolidated bottom-left "BrainWebViz" control panel (reset/search,
  sliders, auto-rotate, nested legend), with in-place search.
- Optional `DEV=1` "work in progress / restarted X ago" deploy banner.
