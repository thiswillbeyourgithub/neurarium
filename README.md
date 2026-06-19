# Neurarium

> [!WARNING]
> **Work in progress, and very probably wrong.** Neurarium is under active
> development and far from complete. None of the anatomy has been reviewed or
> sourced yet, so the regions, shapes, projections, and descriptions very likely
> contain hallucinations and outright errors. Do not rely on any of it.

Neurarium is an interactive 3D brain visualizer that runs in the browser. It
shows brain regions (cortical lobes, basal ganglia / deep nuclei, hindbrain) as
3D shapes and draws arrows for neuron projections between them.

Live at [neurarium.olicorne.org](https://neurarium.olicorne.org).

![Neurarium screenshot](docs/screenshot.png)

## Features

- 3D regions rendered with [three.js](https://threejs.org/), colored per region.
- Curved arrows for directed neuron projections, colored by type (excitatory /
  inhibitory / dopaminergic).
- Controls:
  - **Auto-rotate** the view.
  - **Blow-out (explode)** slider to spread the regions apart and reveal deep
    structures.
  - **Transparency** slider to see through the outer regions.
  - Rotate with one finger / left-drag, pinch to zoom, two-finger drag to pan.
- On-screen debug console via [eruda](https://github.com/liriliri/eruda).

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
| `public/shapes/<id>.json` | One geometry file per region. |
| `public/index.html`, `public/js/` | The three.js viewer and UI. |
| `tools/` | Dev tooling (data generator, dev server, screenshot helper). |
| `docker/` | Deployment (hardened Caddy container). |
| `CLAUDE.md` | Architecture notes and how to extend the anatomy. |

To change which regions or projections are shown, edit `tools/generate_data.py`
and run `python tools/generate_data.py` to regenerate `public/data/` and
`public/shapes/`. See [`CLAUDE.md`](CLAUDE.md) for details.

## Credits

Built with the help of [Claude Code](https://claude.com/claude-code).

## License

[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE).
