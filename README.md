# Brain Visualizer

An interactive 3D brain visualizer that runs in the browser. It shows brain
regions (cortical lobes, basal ganglia / deep nuclei, hindbrain) as 3D shapes
and draws arrows for neuron projections between them.

![Brain visualizer screenshot](docs/screenshot.png)

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
opened directly from disk). From the repository root:

```sh
python -m http.server 8000
```

Then open <http://localhost:8000/>.

## Project layout

| Path | Purpose |
| --- | --- |
| `generate_data.py` | Single source of truth for the anatomy; generates the data below. |
| `data/brain.jsonl` | Region metadata and projections, one JSON object per line. |
| `shapes/<id>.json` | One geometry file per region. |
| `index.html`, `js/` | The three.js viewer and UI. |
| `CLAUDE.md` | Architecture notes and how to extend the anatomy. |

To change which regions or projections are shown, edit `generate_data.py` and
run `python generate_data.py` to regenerate `data/` and `shapes/`. See
[`CLAUDE.md`](CLAUDE.md) for details.

## Credits

Built with the help of [Claude Code](https://claude.com/claude-code).

## License

Licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).
In short: you are free to use, study, modify and redistribute this project, but
modified versions, **including ones you run as a network service**, must make
their complete source available under the same license. See the [`LICENSE`](LICENSE)
file for the full text.
