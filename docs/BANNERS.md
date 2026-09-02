# Error banners & loading overlay

> Reference detail moved out of [`CLAUDE.md`](../CLAUDE.md) to keep that file a terse map. This is the full text for this subsystem.

## Error banners

So a visitor never opens eruda to learn why something broke, failures surface as
red dismissible banners in `#banners` (`js/error-banner.js`): installs `window`
`error` (capture phase, so failed resource loads count) + `unhandledrejection`
handlers (with `file:line` for script errors); exposes `window.showErrorBanner(msg)`
(used by `js/main.js` for the data-load failure). A failed resource whose element
carries `data-optional` is skipped (no banner): a panel's molecule / Wikipedia
illustration self-handles a failed load by dropping its own figure, and an absent
optional image is not an app error to shout about. Banners stack; each has a ×;
identical messages dedupe into one `(×N)`; a `MAX_BANNERS` cap. A `ResizeObserver`
republishes the stack height to `--banners-height`, which `#status` offsets against.

## Loading overlay

A startup progress overlay so a slow first load shows feedback instead of a blank
canvas. `#loading` (static markup in `index.html`, **visible by default** so it paints
before any ES module parses) covers the canvas above every panel/banner; `js/loading.js`
`createLoadingScreen()` exposes `setProgress(frac, label)` (monotone: the bar only ever
moves forward), `notice(text)` (a persistent caveat row, `#loading-note`, see the mesh
budget below), `done()` (fill to 100%, fade out via the `.loaded` opacity transition,
then detach) and `fail()` (detach at once so an error banner takes over). `js/main.js`
drives it: the data fetch fills the first half (`loadBrainData`'s `onProgress` fires per
shape file), SDF meshing the back half (`sdf-pool` `meshAll`'s `onProgress`, captioned
with the region being built), then `done()` fades it out as the assemble intro
begins. Both phases caption a `(done/total)` counter, and the meshing bar is
**cost-weighted** and fed **sub-item** ticks from inside the worker
(`meshSdfToArrays`'s `onProgress` off the field-fill z-loop), so a single heavy
structure (hippocampus, a 112^3 grid) still moves the bar on a slow phone instead of
reading as a freeze. Under the bar a static one-line tease (`.loading-tagline`, i18n
`loading.tagline`) pitches the sourcing angle while the data loads. i18n keys `loading.*`.

**Mesh budget (slow devices).** `js/sdf-quality.js` `createMeshBudget()` keeps the meshing
phase inside a wall-time budget by *measuring* the machine, never sniffing it: `order()`
sorts the specs **cheapest-first** by `estimateSdfCost` (grid samples) so the small nuclei
act as a throughput probe, `note(frac)` projects the remaining work from the observed rate,
and `adjust(spec)` (called by the pool at **dispatch**, so it sees every measurement) scales
down the `resolution` of whatever is still queued. Monotone (only ever coarsens, so detail
never flaps mid-load) and floored at `DEFAULT_MIN_SCALE`. When it fires, `loading.notice()`
shows `loading.reducedQuality` in the amber `.loading-note`: silently shipping coarser
geometry would misrepresent the atlas, so the visitor is told, and the note survives the
"Start exploring" step (which hides only the caption) so it is actually read.

**No startup gate.** The **Sources & provenance** popup (`#sourcing-modal`) is *not* shown
on launch: a visitor just watches the loading bar + its tagline. The modal is wired early
(`wireSourcingModal`, its static intro + grade key rendered at once via
`buildAboutSourcing(null)`, the coverage tally filled once the dataset loads) but only
opens on demand: its own toolbar button (`#sourcing-toggle`), the Legend/About "Sources &
provenance" links, or the guided tour's Sources step.
