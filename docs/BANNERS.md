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
moves forward), `done()` (fill to 100%, fade out via the `.loaded` opacity transition,
then detach) and `fail()` (detach at once so an error banner takes over). `js/main.js`
drives it: the data fetch fills the first half (`loadBrainData`'s `onProgress` fires per
shape file), SDF meshing the back half (`sdf-pool` `meshAll`'s per-item `onItem`,
captioned with each region's name), then `done()` fades it out as the assemble intro
begins. Under the bar a static one-line tease (`.loading-tagline`, i18n `loading.tagline`)
pitches the sourcing angle while the data loads. i18n keys `loading.*`.

**No startup gate.** The **Sources & provenance** popup (`#sourcing-modal`) is *not* shown
on launch: a visitor just watches the loading bar + its tagline. The modal is wired early
(`wireSourcingModal`, its static intro + grade key rendered at once via
`buildAboutSourcing(null)`, the coverage tally filled once the dataset loads) but only
opens on demand: its own toolbar button (`#sourcing-toggle`), the Legend/About "Sources &
provenance" links, or the guided tour's Sources step.
