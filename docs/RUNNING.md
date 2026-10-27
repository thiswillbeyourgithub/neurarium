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

`serve.py` also serves `/derived/effects.json` (the effect index, built from `public/data` by `tools/render_api.py`'s `write_effects` whenever a data file changed, never written into the repo; any other `/derived/` path is a 404). Plain `http.server` lacks it, so the viewer shows a red banner and an empty Effects section.

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

The `--params` string is the URL query parsed by `applyViewParams` in `js/scene/camera.js`.
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

`only`/`view` auto-fit the camera to whatever is visible. `solo=id[,id2]` (with `ghost=0..1`) keeps the rest of the brain ghosted around the set (`tools/sculpt_shot.py`).

Any of these view keys (the one list is `VIEW_KEYS` in `js/boot/query.js`) makes the page a framed view, so auto-rotate turns off unless `autorotate=1`; a query holding only startup flags (`?lang=fr`, `?tour=1`) is not a view and keeps the default spin.

A separate startup flag, `?tour=1`, forces the guided tour to run on every load,
bypassing the once-per-visitor "seen" gate (it still waits for the intro + Sources
gate). Read directly in the tour wiring, not by `applyViewParams`.

`tools/tour_walk.py [--lang en|fr]` walks the whole tour headlessly with real mouse input (Next, tap the ringed target, drag the brain, wheel the panel) and fails on a stuck step, an unclean end state (overlay still up, "seen" unset, click guard still swallowing clicks) or any console error; run it after any UI change (`PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright uv run --with playwright==1.61.0 python tools/tour_walk.py`, about 10 min under SwiftShader).

`node --test tools/tests/tour_anchors.test.mjs` is its sub-second static twin: it imports the tour steps and fails, naming the step, when a selector, `data-tour-*` hook, row id or i18n key a step uses no longer exists (static markup in `index.html`, runtime-built anchors via its `DYNAMIC` token map).

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
the `js/boot/*.js` wirings), and a value seen before its owner is wired is parked and applied the
moment it registers.

#### The keys

| hash | holds |
| --- | --- |
| `#tabs=<kind>:<id>,...` | the open detail tabs, in strip order (the order is state: tabs are drag-reorderable) |
| `#tab=<index>` | which of them is active; omitted when it is the last (where opening the list already lands), `s` = the pinned Settings tab |
| `#popup=about\|legend\|sources\|shortcuts\|whatsnew` | the open popup (a legacy `drugmap` value forwards to `drugs-map.html`, carrying its `dm*` keys) |
| `#dmcat=<cat>,...` / `#dmyear=<from>-<to>` / `#dmhide=<id>,...` / `#dmcolor=<mode>` / `#dmlabels=0` / `#dmspread=0` / `#dmnorm=0` / `#dmsign=0` / `#dmmkt=0` / `#dmsrc=<source>` / `#dmtgt=<key>,...` (`-` = none) | the drugs map page's view (`drugs-map.html#dm...`): class chips, approval-year range (either end may be empty; set by a decade heading's map link), hidden drugs, colour mode, names off, overlap spread off, normalization off, signs off, currently marketed only off, feature source (`tone`, `both`), picked features in axis order (target ids or `tone:<kind>`) |
| `#cam=<az>,<polar>,<dist>[,<tx>,<ty>,<tz>]` | the orbit: degrees around the pivot, distance from it, and the pivot when a focus moved it off centre |
| `#explode=0..1` / `#transparency=0.1..1` | the two sliders |
| `#names=1` / `#arrows=1` / `#inside=1` | Show all names / Show projections / See inside |
| `#rotate=0` / `#anim=0\|1` / `#speed=<multiplier>` | Auto-rotate, Animations, the animation-speed multiplier (1 = the reference pace). Applied from a link but never written: a still view always writes `cam=` (which stops the spin), and the animation pair are persisted personal preferences a shared link should not impose |
| `#colors=sign` | colour arrows by excitatory/inhibitory instead of by transmitter |
| `#collapsed=1` / `#settings=0` | the panel body collapsed / the Controls sub-section closed |
| `#section=drugs\|receptors\|enzymes\|structures\|projections` | the open browse section (empty = all closed) |
| `#q=<query>` | the in-panel search: open with that query (`#q=` opens it empty) |
| `#sim=<id>[:<ratio>],...` | the Simulation tab's picked drugs, in list order (the ratio is omitted at its default of 1) |
| `#drugq=<text>` / `#metab=0` / `#drugsort=<mode>` (`name`, `year`, `halflife`) | the Drugs section's filter box / its "show active metabolites" toggle / its sort switch (class when absent) |
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
