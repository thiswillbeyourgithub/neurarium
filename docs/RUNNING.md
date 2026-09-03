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

The `--params` string is the URL query parsed by `applyViewParams` in `js/main.js`.
`explode` / `transparency` / `names` are ordinary UI state, so they are handed straight
to the url-state views below rather than re-implemented there; the rest is
screenshot-only. The keys also work as deep links:

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

A separate startup flag, `?tour=1`, forces the guided tour to run on every load,
bypassing the once-per-visitor "seen" gate (it still waits for the intro + Sources
gate). Read directly in the tour wiring, not by `applyViewParams`.

### Deep links: the URL fragment IS the UI state

Everything on screen is described by the URL **fragment**, so the address bar is always
the shareable link for the current view: which detail tabs are open and in what order,
which one is active, the popup showing, the scene sliders + toggles, the panel layout,
the open browse section, the search / filter text, and the camera. Copying it is just
selecting the URL bar; there is no copy button.

Both directions run through the `key -> {read, write}` registry in
[`js/url-state.js`](../public/js/url-state.js): the fragment is applied on load and on
`hashchange`, and any UI change writes it back with `history.replaceState` (no
`hashchange` loop, no back/forward spam). Two rules keep links short and safe to paste:

- a view **at its default writes nothing**, so a plain link carries only what actually
  differs;
- a key **missing** from the fragment is never written, so a link that says nothing
  about (say) animations leaves that visitor's own persisted preference alone.

Each control registers its own pair as it is wired (`urlState.register` in
`js/main.js`), and a value seen before its owner is wired is parked and applied the
moment it registers.

#### The keys

| hash | holds |
| --- | --- |
| `#tabs=<kind>:<id>,...` | the open detail tabs, in strip order (the order is state: tabs are drag-reorderable) |
| `#tab=<index>` | which of them is active; omitted when it is the last (where opening the list already lands), `s` = the pinned Settings tab |
| `#popup=about\|legend\|sources\|shortcuts\|whatsnew` | the open popup |
| `#cam=<az>,<polar>,<dist>[,<tx>,<ty>,<tz>]` | the orbit: degrees around the pivot, distance from it, and the pivot when a focus moved it off centre |
| `#explode=0..1` / `#transparency=0.1..1` | the two sliders |
| `#rotate=0` / `#names=1` / `#arrows=1` / `#inside=1` | Auto-rotate / Show all names / Show projections / See inside |
| `#anim=0\|1` / `#speed=<multiplier>` | Animations and the animation-speed multiplier (1 = the reference pace) |
| `#colors=sign` | colour arrows by excitatory/inhibitory instead of by transmitter |
| `#collapsed=1` / `#settings=0` | the panel body collapsed / the Controls sub-section closed |
| `#section=drugs\|receptors\|enzymes\|structures\|projections` | the open browse section (empty = all closed) |
| `#q=<query>` | the in-panel search: open with that query (`#q=` opens it empty) |
| `#drugq=<text>` / `#metab=0` | the Drugs section's filter box / its "show active metabolites" toggle |
| `#panel=1` / `#panel=0` | panel-only reading mode (3D hidden) / force the brain back on |

A tab key is `<kind>:<id>` with kind one of `drug`, `target` (receptors live here too),
`structure`, `connection` (`from->to`), `circuit`, `group`, `enzyme`, `browser`. The id
matches a node's id or its folded, case-insensitive name, so
`#tabs=drug:olanzapine,target:5ht2a` is hand-writable; a structure or connection also
accepts the side-stripped base (`structure:hippocampus`, `connection:cortex->thalamus`),
which pins both hemispheres the way a search pick does.

**The camera is written only while Auto-rotate is off**: a spinning view has no fixed
orientation to capture, and rewriting one every frame would churn history for nothing.
Applying a `cam` therefore turns Auto-rotate off, or the link's view would drift off
immediately. The angles are rounded, since "approximately this view" is what a shared
link means. The image lightbox is deliberately not in the fragment: it shows a picture
reached from a panel, not a state of the UI.

The older single-focus links (`#focusDrug=vortioxetine`, `#focusReceptor=5ht2a`,
`#focusStructure=frontal`, `#focusConnection=cortex->thalamus`, `#focusCircuit=<id>`,
`#focusGroup=<id>`, `#focusTarget=sert`, `#browser=1`) still work as read-only aliases
for one `tabs` entry; the first sync rewrites such a link into the canonical form.
