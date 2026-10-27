# Drugs map

[Version française](README.fr.md)

An interactive map of psychiatric and CNS-active drugs, placed by how similar their [receptor](https://en.wikipedia.org/wiki/Receptor_(biochemistry)) binding profiles are. Drugs that hit the same receptors in the same proportions land close together; drugs with unrelated mechanisms land far apart. It is a companion page of [neurarium](https://neurarium.olicorne.org/), an interactive 3D atlas of the brain for psychiatric neuroscience, and it is built entirely from neurarium's openly served, sourced dataset.

For example, it can lay out the antipsychotics so as to show their dopaminergic, cholinergic and histaminergic affinities (click the picture to open this view):

[![The drugs map: the atypical and conventional antipsychotics placed by their dopamine, cholinergic and histamine binding](screenshot.en.png)](https://drugsmap.olicorne.org/#dmcat=antipsychotic_atypical,antipsychotic_conventional&dmmkt=0&dmtgt=aadc,comt,d1,d2,d3,d4,d5,dat,mao_b,vmat2,ache,bche,m1,m2,m3,m4,m5,nachr_a4b2,nachr_a7,h1,h2,h3,h4)

**Live:** [drugsmap.olicorne.org](https://drugsmap.olicorne.org/) (also at [neurarium.olicorne.org/drugs-map](https://neurarium.olicorne.org/drugs-map))

It was built with the help of [Claude Code](https://claude.com/claude-code).

## What you are looking at

Each drug becomes one vector, then a [principal component analysis](https://en.wikipedia.org/wiki/Principal_component_analysis) (PCA) squeezes all those vectors onto the two axes that spread the drugs out the most. The PCA is recomputed for whatever the filters leave on screen, so filtering to the antipsychotics gives the axes that best separate *antipsychotics*, not the whole roster.

A concrete example of one drug's vector, in "Receptors" mode: one number per target, the [affinity](https://en.wikipedia.org/wiki/Dissociation_constant) `pKi - 5` where `pKi = 9 - log10(Ki in nM)`.

```python
# Ki 1 nM -> pKi 9 -> 4.0 ; Ki 100 nM -> pKi 7 -> 2.0 ; Ki >= 10 µM -> 0 (too weak to matter)
# olanzapine (median Ki: D2 21 nM, 5-HT2A 3.3 nM, H1 2.4 nM, M1 4.7 nM, SERT 2.3 µM)
olanzapine = {"D2": 2.7, "5-HT2A": 3.5, "H1": 3.6, "M1": 3.3, "SERT": 0.6, ...}
```

Only measured affinities count by default: a drug with no measured Ki at all is not on the map, and a binding a source states without a measured Ki is left out (switch off **Measured Ki only** to count it at an assumed 100 nM). By default each vector is scaled to unit length, so the map compares the *shape* of a profile (which targets, in what proportion) rather than raw potency.

Controls (all folded boxes above the plot):

- **Place drugs by:** receptor affinities, net transmitter tone (the drug's signed effect on each [neurotransmitter](https://en.wikipedia.org/wiki/Neurotransmitter) system), or both.
- **Signed:** an [agonist](https://en.wikipedia.org/wiki/Agonist) and an [antagonist](https://en.wikipedia.org/wiki/Receptor_antagonist) of the same receptor point in opposite directions.
- **Targets:** restrict the vectors to some targets; pick one or two and they become the axes themselves (no PCA).
- **Filter points by:** drug class, first approval year, marketed only.
- **Colour by:** class, [Neuroscience-based Nomenclature](https://nbn2r.com/), approval year, originator lab, [metabolism](https://en.wikipedia.org/wiki/Drug_metabolism), or Ki coverage.
- **Plot:** scroll / pinch to zoom, drag to pan, two-finger twist (or the rotate gesture) to rotate, fullscreen button.

Click a drug to open it in neurarium's 3D atlas (its full panel: bindings with their quoted sources, metabolism, history...). Right-click or long-press hides it from the map. The whole view lives in the address bar, so a URL is a shareable link to exactly what is on screen.

## Where the data comes from

Everything comes from neurarium's public data files (`/data/*.jsonl`, described in [`llms.txt`](https://neurarium.olicorne.org/llms.txt), with one Markdown page per node under [`/api/`](https://neurarium.olicorne.org/api/)). The bindings come from Stahl's Prescriber's Guide, the [PDSP Ki database](https://pdspdb.unc.edu/databases/kidb.php), the [IUPHAR/BPS Guide to Pharmacology](https://en.wikipedia.org/wiki/Guide_to_Pharmacology) and Wikipedia, each binding carrying its quoted source and a provenance grade, which you can inspect by clicking the drug. This page is an example of what can be built on top of that open dataset.

**Caveats:** this is an exploratory visualisation, not medical advice. Ki values are measured [in vitro](https://en.wikipedia.org/wiki/In_vitro), often on rodent receptors, and say nothing about the dose actually reached in a brain; a PCA keeps only the two most spread-out directions, so two drugs close on the map can still differ on a target the axes do not capture (the axis captions name which targets each axis weighs most).

## Hosting

The page is not a separate project: it is `public/drugs-map.html` in the neurarium repository, booted by `public/js/drugs-map-main.js`, and it reuses the viewer's own modules (the data loader, the URL state, the theme and language switch). It loads none of the 3D code. The neurarium container serves it at `/drugs-map`.

`drugsmap.olicorne.org` is the same container behind the outer reverse proxy, which rewrites the root to the page, so the address bar keeps showing `drugsmap.olicorne.org` while every asset is served from neurarium. With Caddy as the outer proxy:

```caddy
drugsmap.olicorne.org {
	# Internal rewrite: the address bar stays drugsmap.olicorne.org/ (the #view hash is kept)
	rewrite / /drugs-map.html
	# Keep the 3D app off this host: its entry page goes to the real domain
	redir /index.html https://neurarium.olicorne.org/ 301
	reverse_proxy <the same upstream as the neurarium.olicorne.org block>
}
```

The picture at the top is rendered by `uv run tools/shot_drugs_map.py` (its view is the script's `DEFAULT_HASH`): rerun it whenever the map's look changes.

Links from the map to the 3D atlas detect this case (the page served at `/`) and point at `https://neurarium.olicorne.org/` instead of a relative path. Visits are counted by the same umami site as neurarium, under the `drugsmap.olicorne.org` hostname.
