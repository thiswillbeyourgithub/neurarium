# neurarium

> [!WARNING]
> **Work in progress, and very probably wrong.** neurarium is under active
> development and far from complete. None of the anatomy has been reviewed or
> sourced yet, so the regions, shapes, projections, and descriptions very likely
> contain hallucinations and outright errors. Do not rely on any of it.

neurarium is an interactive 3D brain visualizer that runs in the browser. It
shows brain regions (cortical lobes, basal ganglia / deep nuclei, hindbrain) as
3D shapes and draws arrows for neuron projections between them.

Live at [neurarium.olicorne.org](https://neurarium.olicorne.org).

![neurarium screenshot](docs/screenshot.png)

## Features

### Visualization

- Brain regions (cortical lobes, basal ganglia / deep nuclei, diencephalon,
  limbic, hindbrain) as procedurally shaped 3D meshes: gyrified cortex, smooth
  deep nuclei, foliated cerebellum, and swept tubes for the caudate, brainstem,
  hippocampus, cingulate, and fornix.
- At rest the regions lock together into a whole brain; an intro animation
  assembles them from an exploded state on load.
- Curved arrows for directed neuron projections, colored by type (excitatory,
  inhibitory, dopaminergic, cholinergic, neuroendocrine), with a cone at the
  target end (both ends for reciprocal / commissural pathways).

### Exploring the anatomy

- **Click a region** to open an info panel with its name, group, a **Wikipedia
  link**, and the list of pathways touching it; click a pathway row to jump to it.
- **Click an arrow** to see that pathway's details: route, type, neurotransmitter,
  a one-line description, and its **sources**.
- **Search** (the magnifier) filters both regions (by name) and connections (by
  pathway label) and frames whatever you pick.
- **Legend** isolates what you click: a region (both hemispheres), a whole
  category, a named **functional circuit**, or a single **neurotransmitter** (only
  those pathways and their endpoints stay lit, everything else fades). A separate,
  off-by-default **Hypothetical pathways** section reveals speculative / less-
  certain connections, drawn as dotted arrows.
- **Hover / tap** a region to show its floating name; a **Show all names** button
  labels everything at once, and a **Hide projections** button clears the arrows.

### Controls

- **Auto-rotate** the view (on by default; stops as soon as you pick something).
- **Separate** slider spreads the regions apart to reveal the deep structures
  (**Shift + scroll** drives it too; plain scroll zooms).
- **Transparency** slider to see through the outer regions.
- Rotate with one finger / left-drag, pinch to zoom, two-finger drag to pan;
  double-click a region to frame it, or empty space to recenter.

### Data & sourcing

- The anatomy is plain **structured data**: `public/data/brain.jsonl` (one JSON
  object per line: regions, projections, named circuits, and a self-describing
  `meta` record carrying the colour and legend-heading maps) plus one geometry
  file per shape under `public/data/shapes/`. It is generated from a single source
  (`tools/generate_data.py`) and easy to consume from another engine.
- Every projection carries a **neurotransmitter** and a list of **sources**
  (citations; a verified link renders as a hyperlink, an unfilled one as plain
  text). Every region links to its **Wikipedia** article.

### Deep links & screenshots

- The view is URL-addressable: `?only=`, `?view=`, `?explode=`, `?transparency=`,
  `?names=all`, `?autorotate=1`, `?ui=0` (see the table in
  [`CLAUDE.md`](CLAUDE.md)). `tools/shot.py` uses the same params to render PNGs.
- On-screen debug console via [eruda](https://github.com/liriliri/eruda), loaded
  only in dev or with `?debug`; runtime errors otherwise surface as dismissible
  on-screen banners.

## Roadmap

Planned directions, none implemented yet and the order is not fixed:

- **Animations**: show activity and signal flow along the pathways (e.g. pulses
  travelling down a projection), beyond the current assemble intro.
- **Brain receptors**: where the neurotransmitter receptor families sit, layered
  onto the regions and pathways.
- **Drugs**: how common psychoactive and therapeutic compounds act on those
  receptors and pathways.
- **Pathologies**: how disorders map onto the regions, circuits, and
  neurotransmitter systems.

## Running

The page loads its data with `fetch()`, so it must be served over HTTP (not
opened directly from disk). The served site is `public/`. From the repository
root:

```sh
python tools/serve.py            # serves public/ with caching disabled
# or: cd public && python -m http.server 8000
```

Then open <http://localhost:8000/>.

## Project layout

| Path | Purpose |
| --- | --- |
| `public/` | The served site (and the only web-exposed directory). |
| `tools/generate_data.py` | Single source of truth for the anatomy; generates the data below. |
| `public/data/brain.jsonl` | Region metadata and projections, one JSON object per line. |
| `public/data/shapes/<id>.json` | One geometry file per region. |
| `public/index.html`, `public/js/` | The three.js viewer and UI. |
| `tools/` | Dev tooling (data generator, dev server, screenshot helper). |
| `docker/` | Deployment (hardened Caddy container). |
| `ARCHITECTURE.md` | High-level architecture: data flow, module graph, boot sequence. |
| `CLAUDE.md` | The exhaustive file-by-file map and how to extend the anatomy. |

To change which regions or projections are shown, edit `tools/generate_data.py`
and run `python tools/generate_data.py` to regenerate `public/data/`
(`brain.jsonl` + `shapes/`). See [`CLAUDE.md`](CLAUDE.md) for details.

## Stack

Deliberately lightweight, with a small attack surface and no build step:

- **Frontend**: vanilla ES modules + [three.js](https://threejs.org/) loaded via
  an import map. three.js is vendored under `public/vendor/three`, so the page
  executes no third-party script at runtime and works offline. No framework, no
  bundler, no `node_modules`.
- **Data**: `tools/generate_data.py` (Python standard library only) emits the
  anatomy as `public/data/brain.jsonl` + `public/data/shapes/*.json`, fetched at
  runtime. The plain JSONL/JSON format is easy to consume from another engine.
- **Serving**: a hardened [Caddy](https://caddyserver.com/) container (non-root,
  read-only rootfs, dropped capabilities, resource limits) that sends a strict
  Content-Security-Policy; a reverse proxy terminates TLS in front of it.
- **Debugging**: an [eruda](https://github.com/liriliri/eruda) on-screen console,
  loaded only in dev or with `?debug` so it never ships to normal visitors.

## Credits

Built with the help of [Claude Code](https://claude.com/claude-code).

## License

[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE).
