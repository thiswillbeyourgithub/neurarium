# neurarium

**An interactive 3D atlas that gathers what we know about the human brain (its
regions, the pathways between them, the receptors they carry, and the drugs that
act on them) and reorganizes it into one explorable map, where every fact is
graded by how trustworthy it is.**

> [!WARNING]
> **Work in progress. It probably contains many mistakes for now.** neurarium is
> under active development and far from complete. None of the anatomy has been
> reviewed or sourced yet, so the regions, shapes, projections, and descriptions
> very likely contain hallucinations and outright errors. The drug data is
> machine-extracted from a single source (Stahl's Prescriber's Guide) and likewise
> unreviewed, so the classes, targets, and bindings may be wrong or incomplete. Do
> not rely on any of it, and never use it for medical decisions.

Live at [neurarium.olicorne.org](https://neurarium.olicorne.org).

![neurarium screenshot](docs/screenshot.png)

neurarium is not a textbook and not a raw database. It takes facts about the brain
that normally live scattered across atlases, pathway diagrams, receptor tables, and
drug monographs, and lays them onto a single 3D model you can rotate, pull apart,
search, and click through. The point is to make the *relationships* between those
facts (which region projects where, which receptor sits in which structure, what a
given drug does and to what) something you can see at a glance rather than
reconstruct in your head. And because the dataset is machine-assembled, every claim
it shows carries a [source grade](#every-fact-is-graded) so you always know how much
to trust it.

## Contents

- [What you can explore](#what-you-can-explore)
- [Every fact is graded](#every-fact-is-graded)
- [Built to be reused](#built-to-be-reused)
- [Roadmap](#roadmap)
- [Feedback](#feedback)
- [Running](#running)
- [Stack](#stack)
- [Credits](#credits)
- [License](#license)

## What you can explore

**The brain, as one model.** Cortical lobes, basal ganglia and deep nuclei,
diencephalon, limbic structures, and the hindbrain, all as procedurally shaped 3D
meshes that lock together into a whole brain and blow apart on a slider to reveal
what is hidden inside. Rotate it, make it transparent, peel away the near side to
see the deep nuclei, or isolate any one structure to study it alone.

**The wiring between regions.** Directed neuron projections are drawn as curved
arrows, colored by type (excitatory, inhibitory, dopaminergic, and so on) or
recolored by their excitatory / inhibitory potential. Click any pathway for its
route, neurotransmitter, and sources. Named **functional circuits** (the direct
pathway, the Papez memory loop, ...) light up on demand and play a traveling pulse
so you can watch a signal flow around the loop.

**The receptors each region carries.** A browsable list of neurotransmitter
receptors and other molecular targets (transporters, enzymes, ion channels). Focus
one and the brain dims to just the structures that express it, scattered with
glowing dots, alongside its mechanism class, its excitatory / inhibitory sign, and
where it is found, plus every drug that acts on it.

**What drugs do to the brain.** A filterable list of psychiatric drugs (from
Stahl's Prescriber's Guide). Focus one and the brain animates what it does:
effect-colored dots (boost / block / modulate) pulse over the regions it touches,
and beads flow along the transmitter systems it works through. The panel shows its
molecular structure, class, nomenclature, the targets it binds and how, and the
source behind each binding.

**All of it is searchable and linkable.** Search across regions, pathways,
receptors, and drugs at once; pivot from a drug to its whole class; jump from a
target to every drug that hits it. The whole view is URL-addressable, so any state
(a framed structure, an exploded view, a specific angle) is a shareable deep link.

## Every fact is graded

The dataset is large and machine-assembled, so the honest question for any single
claim is *how do we know this?* neurarium answers it inline: every source and
reference shown in a detail panel carries a small colored **provenance pill**
grading how trustworthy that attribution is. Hover (or tap) any pill for the full
explanation. The grades, from weakest to strongest:

- **grey `?` (LLM-only)**: produced by a language model from memory, not checked
  against any document, so it may be a hallucination.
- **yellow `~` (sourced)**: written by a model that was given the source document
  (e.g. Stahl's guide), but the specific claim was not quote-verified.
- **green `✓` (verified)**: a model extracted a quote, the quote was
  *programmatically* confirmed to appear in the cited source, and a second model
  agreed it supports the claim. This is the **highest** grade available and is
  **still model-driven**, so it can still be wrong: going further would take
  considerable human effort, itself error-prone, and is out of scope here.
- **orange `NOSOURCE`**: there is no source or reference for that claim yet.

The grade is part of the data, not a label bolted on after, so a source is upgraded
as it is checked. This is why the coverage below is a real, programmatic count and
not a slogan:

<!-- SOURCING_STATS:START (generated by tools/update_readme_stats.py; do not edit by hand) -->

**70% of the 943 factual claims in the dataset are sourced or verified.** This is a programmatic count (`tools/update_readme_stats.py`, from the emitted data), not hand-typed:

| Claim kind | Sourced or verified |
| --- | --- |
| Drug target bindings | 403 / 429 (94%) |
| Drug nomenclature (NbN) | 113 / 116 (97%) |
| Drug descriptions | 140 / 158 (89%) |
| Neuron pathways | 0 / 107 (0%) |
| Receptor classifications | 0 / 56 (0%) |
| Target classifications | 0 / 25 (0%) |
| Brain-region anatomy | 0 / 52 (0%) |
| Wikipedia reference links | 296 / 298 (99%) |

<!-- SOURCING_STATS:END -->

The drug bindings lead because they go through the full quote-verification gate; the
anatomy, pathways, and references are the current frontier (all still LLM-only). The
same grade key and coverage bar live in the app's About panel.

**A note on the sources.** The reference works the dataset is checked against
(Stahl's *Prescriber's Guide* and the other psychopharmacology / neuroscience
books) are copyrighted, so they are **not** committed to this repository, only the
tooling that uses them is. So anyone holding a copy can reproduce the extraction
and confirm every `✓`-graded quote for themselves; nothing about the sourcing is
hidden, only the copyrighted text is left out. Drop the Stahl PDF into
`sources/books/stahl/` and three committed scripts rebuild exactly what the quote
gate checks against:

```sh
uv run tools/pdf_to_pages.py    # the PDF -> one Markdown file per page
uv run tools/build_index.py     # the per-drug page index
python tools/check_data.py      # re-verifies every quote is on its cited page
```

## Built to be reused

The anatomy is plain **structured data**, kept deliberately separate from the
rendering code. Under `public/data/` it is split by record type (`structures`,
`projections`, `circuits`, `receptors`, `drugs`, one JSON object per line) next to a
self-describing `meta.json` carrying the colour and legend maps, with one geometry
file per shape. It is generated from a single source of truth
(`tools/generate_data.py`, with the drug list in `tools/drugs_data.json`), so the
plain JSONL/JSON is easy to consume from another engine. Each projection carries a
neurotransmitter and its sources; each region, receptor, and drug links to its
Wikipedia article; each drug records its class, nomenclature, and the molecular
targets it binds, extracted strictly from the cited text.

For the full picture of how it fits together (data flow, module graph, boot
sequence) see [`ARCHITECTURE.md`](ARCHITECTURE.md), and for the exhaustive
file-by-file map and how to extend the dataset see [`CLAUDE.md`](CLAUDE.md).

## Roadmap

Planned directions, none implemented yet and the order is not fixed:

- **More animation**: build on the assemble intro, the circuit traveling-pulse, and
  the per-drug effect dots to show wider activity and signal flow across the brain.
- **Pathologies**: how disorders map onto the regions, circuits, and
  neurotransmitter systems.
- **Verify the sources**: every citation currently carries a placeholder **TODO**
  url; replace each with a verified DOI/link, and lift each fact's provenance grade
  from grey toward green as it is checked (the anatomy and pathways are the gap).

## Feedback

Found a bug, an anatomical or pharmacological **inaccuracy**, or have a **feature
request**? Please **open an issue** on this repository. Given the work-in-progress
warning above, corrections to the regions, projections, receptor, and drug data are
especially welcome.

## Running

The page loads its data with `fetch()`, so it must be served over HTTP (not opened
directly from disk). The served site is `public/`. From the repository root:

```sh
python tools/serve.py            # serves public/ with caching disabled
# or: cd public && python -m http.server 8000
```

Then open <http://localhost:8000/>.

## Stack

Deliberately lightweight, with a small attack surface and no build step:

- **Frontend**: vanilla ES modules + [three.js](https://threejs.org/) loaded via an
  import map. three.js is vendored under `public/vendor/three`, so the page executes
  no third-party script at runtime and works offline. No framework, no bundler, no
  `node_modules`.
- **Data**: `tools/generate_data.py` (Python standard library only) emits the
  anatomy as the `public/data/` files (`meta.json` + `*.jsonl`) +
  `public/data/shapes/*.json`, fetched at runtime. The plain JSONL/JSON format is
  easy to consume from another engine.
- **Serving**: a hardened [Caddy](https://caddyserver.com/) container (non-root,
  read-only rootfs, dropped capabilities, resource limits) that sends a strict
  Content-Security-Policy; a reverse proxy terminates TLS in front of it.
- **Debugging**: an [eruda](https://github.com/liriliri/eruda) on-screen console,
  loaded only in dev or with `?debug` so it never ships to normal visitors.

## Credits

Built by [Olivier Cornelis](https://olicorne.org/) (developer and psychiatrist) with
the help of [Claude Code](https://claude.com/claude-code). Drug descriptions and
molecular-structure images come from Wikipedia, used under
[CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/).

## License

[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE).
