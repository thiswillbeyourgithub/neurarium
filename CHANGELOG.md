# Changelog

All notable changes to this project are recorded here. The project follows
[semantic versioning](https://semver.org/) (MAJOR.MINOR.PATCH); the current
version is the single source of truth in [`version.js`](version.js) and is shown
in the app's panel header. Bump `version.js` and add an entry here in the same
change.

Built with the help of Claude Code.

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
