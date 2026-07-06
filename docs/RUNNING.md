# Running & screenshots

> Reference detail moved out of [`CLAUDE.md`](../CLAUDE.md) to keep that file a terse map. This is the full text for this subsystem.

## Running

The data is loaded with `fetch()`, so serve over HTTP (`file://` fails CORS). The
served site is `public/`. From the repo root:

```
python tools/serve.py        # http://localhost:8000/ (recommended)
# or: cd public && python -m http.server 8000
```

Prefer `tools/serve.py`: it sends `Cache-Control: no-store`, so the browser
refetches every ES module each reload. Plain `http.server` lets browsers heuristic-
cache JS modules, which can serve a stale `js/*.js` and cause baffling mismatch
crashes; if you see one after editing JS, hard-reload (Ctrl/Cmd+Shift+R) or use `serve.py`.

Debugging: [eruda](https://github.com/liriliri/eruda) on-screen console, **gated**
on `?debug=1` exactly (normal visitors never download it), vendored same-origin at
`public/vendor/eruda/eruda.js`, pinned top-right. Runtime errors otherwise surface
via the red error banners.

### Screenshots & deep-link view params

`tools/shot.py` (Playwright) renders the page to a PNG: serves `public/` with
`tools/serve.py`, drives headless Chromium (SwiftShader GL flags baked in, so
WebGL renders without a display), captures the canvas. Bare run writes
`docs/images/screenshot.png` (a static still). The README's animated hero is `docs/images/preview.gif`,
recorded by `tools/demos/neurarium.py` (see the `tools/demos/` entry above).

```
python tools/shot.py
python tools/shot.py --params "explode=0.5&view=iso" --out /tmp/brain.png
python tools/shot.py --params "only=putamen_R&view=iso" --out /tmp/putamen.png
```

Needs `playwright` + `playwright install chromium` once (or `uv run tools/shot.py`,
inline deps). `--headed` opens a real window; `--wait` ms before capture (default 6000).

The `--params` string is the URL query parsed by `applyViewParams` in
`js/main.js`, so the keys also work as deep links:

| key | effect |
| --- | --- |
| `only=id[,id2]` | show only these structure ids (others + arrows hidden) |
| `view=front\|back\|left\|right\|top\|bottom\|iso` | frame the visible meshes |
| `explode=0..1` | blow-out amount (also moves the slider) |
| `transparency=0..1` | material opacity |
| `names=all` | show every label |
| `autorotate=1` | spin (deep links default auto-rotate off; this forces it on) |
| `ui=0` | hide the panels + legend (clean shape shots) |

`only`/`view` auto-fit the camera to whatever is visible.

### Node deep links (URL hash)

A URL **hash** focuses one node on load (and on `hashchange`), exactly as picking it
from search would (opens its detail tab + focuses the 3D). Parsed by `applyDeepLink`
in `js/main.js`; the value matches the node's id or (folded, case-insensitive) name:

| hash | focuses |
| --- | --- |
| `#focusDrug=vortioxetine` | a drug |
| `#focusReceptor=5ht2a` / `#focusTarget=sert` | a receptor / non-receptor target |
| `#focusStructure=frontal` | a structure (both hemispheres; use the side-stripped base id/name) |
| `#focusConnection=cortex->thalamus` | a projection (both sides) |
| `#focusCircuit=<id>` / `#focusGroup=<id>` | a circuit / projection group |

The inverse also holds automatically: focusing any node rewrites the URL hash to its
deep link via `history.replaceState` (`syncHashToFocus`, built from `currentDeepLink`),
so the address bar is always the shareable link for what is on screen (no copy button;
`replaceState` avoids both a `hashchange` loop and back/forward history spam).
