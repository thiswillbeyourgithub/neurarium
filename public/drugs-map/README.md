# DrugsMap

[Version française](README.fr.md)

An interactive map of psychiatric and CNS-active drugs, placed by how similar their [receptor](https://en.wikipedia.org/wiki/Receptor_(biochemistry)) binding profiles are. Drugs that hit the same receptors in the same proportions land close together; drugs with unrelated mechanisms land far apart. It is based on the data of [neurarium](https://neurarium.olicorne.org/), by the same author, an interactive atlas of the brain for psychiatric neuroscience. It is also meant as a worked example of how to reuse neurarium's open data in a tool of your own (see [Where the data comes from](#where-the-data-comes-from)).

For example, it can lay out the antipsychotics so as to show their dopaminergic, cholinergic and histaminergic affinities (click the picture to open this view):

[![DrugsMap: the atypical and conventional antipsychotics placed by their dopamine, cholinergic and histamine binding](screenshot.en.png)](https://drugsmap.olicorne.org/#dmcat=antipsychotic_atypical,antipsychotic_conventional&dmmkt=0&dmtgt=aadc,comt,d1,d2,d3,d4,d5,dat,mao_b,vmat2,ache,bche,m1,m2,m3,m4,m5,nachr_a4b2,nachr_a7,h1,h2,h3,h4)

Here it is in motion: every drug by its whole binding profile, then the antipsychotic presets (D2 against 5-HT2A, then the side-effect receptors), hovering a few drugs:

https://github.com/user-attachments/assets/567c9c1e-7af2-4b72-bb72-bd8a5282450c

**Live:** [drugsmap.olicorne.org](https://drugsmap.olicorne.org/) (also at [neurarium.olicorne.org/drugs-map](https://neurarium.olicorne.org/drugs-map))

**Contents:** [Presets](#presets) · [What you are looking at](#what-you-are-looking-at) · [Where the data comes from](#where-the-data-comes-from) · [Hosting](#hosting)

## Presets

The **Presets** box at the top of the page loads a ready-made view in one click. Click a picture to open that view live (the **Default view** preset brings the map back to its defaults):

<!-- presets:start -->
| | |
| --- | --- |
| [![Antipsychotics: dopamine](presets/ap_dopamine.en.png)](https://drugsmap.olicorne.org/#dmcat=antipsychotic_atypical,antipsychotic_conventional&dmcolor=nbn&dmtgt=d1,d2,d3,d4,d5,dat)<br>**Antipsychotics: dopamine** | [![Antipsychotics: D2 vs 5-HT2A](presets/ap_d2_5ht2a.en.png)](https://drugsmap.olicorne.org/#dmcat=antipsychotic_atypical,antipsychotic_conventional&dmtgt=d2,5ht2a)<br>**Antipsychotics: D2 vs 5-HT2A** |
| [![Antipsychotics: side-effect receptors](presets/ap_side.en.png)](https://drugsmap.olicorne.org/#dmcat=antipsychotic_atypical,antipsychotic_conventional&dmtgt=h1,m1,alpha1a,5ht2c)<br>**Antipsychotics: side-effect receptors** | [![Antipsychotics: body effects](presets/ap_effects.en.png)](https://drugsmap.olicorne.org/#dmcat=antipsychotic_atypical,antipsychotic_conventional&dmsrc=effects)<br>**Antipsychotics: body effects** |
| [![Antidepressants: SERT vs NET](presets/ad_sert_net.en.png)](https://drugsmap.olicorne.org/#dmcat=ssri,snri,tricyclic,maoi,antidepressant_other&dmtgt=sert,net)<br>**Antidepressants: SERT vs NET** | [![Antidepressants by mechanism](presets/ad_profile.en.png)](https://drugsmap.olicorne.org/#dmcat=ssri,snri,tricyclic,maoi,antidepressant_other&dmcolor=nbn)<br>**Antidepressants by mechanism** |
| [![Sleep and anxiety](presets/sleep.en.png)](https://drugsmap.olicorne.org/#dmcat=benzodiazepine,hypnotic,anxiolytic,antihistamine)<br>**Sleep and anxiety** | [![All drugs by neurotransmitter tone](presets/all_tone.en.png)](https://drugsmap.olicorne.org/#dmsrc=tone)<br>**All drugs by neurotransmitter tone** |
| [![Antihistamines: H1 vs M1](presets/antihistamines.en.png)](https://drugsmap.olicorne.org/#dmcat=antihistamine&dmtgt=h1,m1)<br>**Antihistamines: H1 vs M1** | [![Psychedelics: serotonin receptors](presets/psychedelics.en.png)](https://drugsmap.olicorne.org/#dmcat=recreational&dmmkt=0&dmtgt=5ht2a,5ht2c,5ht1a,5ht2b)<br>**Psychedelics: serotonin receptors** |
| [![MAOIs: MAO-A vs MAO-B](presets/maois.en.png)](https://drugsmap.olicorne.org/#dmcat=maoi&dmtgt=mao_a,mao_b)<br>**MAOIs: MAO-A vs MAO-B** | [![Opioids: mu, kappa, delta](presets/opioids.en.png)](https://drugsmap.olicorne.org/#dmcat=opioid&dmtgt=mu,kappa,delta)<br>**Opioids: mu, kappa, delta** |
| [![Stimulants: DAT vs NET](presets/stimulants.en.png)](https://drugsmap.olicorne.org/#dmcat=stimulant&dmtgt=dat,net)<br>**Stimulants: DAT vs NET** |  |
<!-- presets:end -->

## What you are looking at

Each drug becomes one vector, then a [principal component analysis](https://en.wikipedia.org/wiki/Principal_component_analysis) (PCA) squeezes all those vectors onto the two axes that spread the drugs out the most. The PCA is recomputed for whatever the filters leave on screen, so filtering to the antipsychotics gives the axes that best separate *antipsychotics*, not the whole roster.

A concrete example of one drug's vector, in "Receptors" mode: one number per target, the [affinity](https://en.wikipedia.org/wiki/Dissociation_constant) `pKi - 5` where `pKi = 9 - log10(Ki in nM)`.

```python
# Ki 1 nM -> pKi 9 -> 4.0 ; Ki 100 nM -> pKi 7 -> 2.0 ; Ki >= 10 µM -> 0 (too weak to matter)
# olanzapine (median Ki: D2 21 nM, 5-HT2A 3.3 nM, H1 2.4 nM, M1 4.7 nM, SERT 2.3 µM)
olanzapine = {"D2": 2.7, "5-HT2A": 3.5, "H1": 3.6, "M1": 3.3, "SERT": 0.6, ...}
```

Only measured affinities count by default: a drug with no measured Ki at all is not on the map, and a binding a source states without a measured Ki is left out (switch off **Measured Ki only** to count it at an assumed 100 nM). By default each vector is scaled to unit length, so the map compares the *shape* of a profile (which targets, in what proportion) rather than raw potency.

Controls (boxes above the plot):

- **Presets:** ready-made views, one click each (see [Presets](#presets)).

- **Place drugs by:** any combination of receptor affinities, neurotransmitter tone (the drug's signed effect on each [neurotransmitter](https://en.wikipedia.org/wiki/Neurotransmitter) system) and body effects (beta: the effects its receptors may produce, inferred from the sourced receptor effects and the direction of each binding, weighted by affinity).
- **Signed:** an [agonist](https://en.wikipedia.org/wiki/Agonist) and an [antagonist](https://en.wikipedia.org/wiki/Receptor_antagonist) of the same receptor point in opposite directions.
- **Targets:** restrict the vectors to some targets; pick one or two and they become the axes themselves (no PCA).
- **Filter points by:** drug class, first approval year, marketed only.
- **Colour by:** class, [Neuroscience-based Nomenclature](https://nbn2r.com/), approval year, originator lab, [metabolism](https://en.wikipedia.org/wiki/Drug_metabolism), or Ki coverage.
- **Plot:** scroll / pinch to zoom, drag to pan, two-finger twist (or the rotate gesture) to rotate; the ⋮ menu at the top right goes fullscreen, resets the rotation or copies the plot as an image.

Click a drug to open it in neurarium's 3D atlas (its full panel: bindings with their quoted sources, metabolism, history...). Right-click or long-press hides it from the map. The whole view lives in the address bar, so a URL is a shareable link to exactly what is on screen.

## Where the data comes from

Everything comes from neurarium's public data files (`/data/*.jsonl`, described in [`llms.txt`](https://neurarium.olicorne.org/llms.txt), with one Markdown page per node under [`/api/`](https://neurarium.olicorne.org/api/)). The bindings come from Stahl's Prescriber's Guide, the [PDSP Ki database](https://pdspdb.unc.edu/databases/kidb.php), the [IUPHAR/BPS Guide to Pharmacology](https://en.wikipedia.org/wiki/Guide_to_Pharmacology) and Wikipedia, each binding carrying its quoted source and a provenance grade, which you can inspect by clicking the drug. This page is an example of what can be built on top of that open dataset.

**Caveats:** this is an exploratory visualisation, not medical advice. Ki values are measured [in vitro](https://en.wikipedia.org/wiki/In_vitro), often on rodent receptors, and say nothing about the dose actually reached in a brain; a PCA keeps only the two most spread-out directions, so two drugs close on the map can still differ on a target the axes do not capture (the axis captions name which targets each axis weighs most).

## Hosting

<details>
<summary>How the page is hosted, and how its pictures are made (click to unfold)</summary>

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

The picture at the top and the preset pictures (with the Presets section listing them) are rendered by `uv run tools/shot_drugs_map.py` (the top view is the script's `DEFAULT_HASH`, the presets are read off the page's buttons): rerun it whenever the map's look or its presets change.

The page is installable as its own app (`drugs-map.webmanifest`, launching at `/drugs-map`) from either host.

Links from the map to the 3D atlas detect this case (the page served at `/`, or on the `drugsmap.olicorne.org` host) and point at `https://neurarium.olicorne.org/` instead of a relative path. Visits are counted by the same umami site as neurarium, under the `drugsmap.olicorne.org` hostname.

</details>

This page was built with the help of [Claude Code](https://claude.com/claude-code).
