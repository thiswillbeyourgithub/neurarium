<p align="center">
  <img src="docs/images/neurarium-icon.svg" alt="neurarium logo" width="120" height="120">
</p>

# neurarium

*Read this in [French / en français](README.fr.md).*

neurarium is my modest attempt at a **3D brain encyclopedia** where every fact is
backed by a reputable source (a reference medical textbook, an online pharmacology
database, a research paper), reorganized into an intuitive 3D brain you can rotate,
pull apart, search, and click through.

Brain knowledge normally lives scattered across atlases, pathway diagrams, receptor
tables, and drug monographs. neurarium lays it onto a single 3D model so the
*relationships* (which region projects where, which receptor sits in which structure,
what a drug does and to what) are visible at a glance instead of reconstructed in your
head. Because the dataset is machine-assembled, every fact carries a colored grade
telling you how well it is sourced, so you always know how much to trust it.

Live at **[neurarium.olicorne.org](https://neurarium.olicorne.org)**.

[![neurarium demo](docs/images/preview.webp)](https://neurarium.olicorne.org)

> [!IMPORTANT]
> <!-- SOURCED_HEADLINE:START --><b>97% of the 10321 knowledge nodes are sourced or verified</b><!-- SOURCED_HEADLINE:END -->
> in the shipped dataset, and every fact in the app carries a provenance grade you
> can inspect (see [How does the sourcing work?](#how-does-the-sourcing-work)).

> [!WARNING]
> **Work in progress: it very likely contains mistakes.** The anatomy (regions,
> shapes, projections, descriptions) is not yet reviewed or sourced and may contain
> model hallucinations; the drug data is machine-extracted (psychiatric drugs from
> Stahl's *Prescriber's Guide*, other substances from measured PDSP Ki affinities) and
> likewise unreviewed. neurarium is an early tool for exploring and learning or finding sources but **not** as a
> primary clinical reference: do not rely on it, and never bet a patient's care solely on it.

> [!TIP]
> **AI-ready:** paste [`neurarium.olicorne.org/llms.txt`](https://neurarium.olicorne.org/llms.txt) once into Claude, ChatGPT, Le Chat, Gemini or another assistant and ask it to remember the site: it can then look up and check neurarium's facts against their quoted sources (see [Can I ask an AI assistant about it?](#can-i-ask-an-ai-assistant-about-it)).

## More demos

Click a picture to play its demo (they are stills here so the page stays light).

<table>
<tr>
<td width="50%"><a href="docs/images/demo-anatomy.webp"><img src="docs/images/demo-anatomy.poster.webp" alt="demo-anatomy (click to play)"></a><br>

Anatomy: blow the brain apart, isolate the hippocampus, play the Papez circuit, then fluoxetine's serotonergic flow.

</td>
<td width="50%"><a href="docs/images/demo-receptor.webp"><img src="docs/images/demo-receptor.poster.webp" alt="demo-receptor (click to play)"></a><br>

A receptor: where 5-HT2A is expressed, every drug that binds it, then LSD picked from that list.

</td>
</tr>
<tr>
<td width="50%"><a href="docs/images/demo-compare.webp"><img src="docs/images/demo-compare.poster.webp" alt="demo-compare (click to play)"></a><br>

Two antipsychotics compared: haloperidol's binding profile, then clozapine's much broader one.

</td>
<td width="50%"><a href="docs/images/demo-drugsmap.webp"><img src="docs/images/demo-drugsmap.poster.webp" alt="demo-drugsmap (click to play)"></a><br>

[DrugsMap](https://drugsmap.olicorne.org/): every drug placed by its binding profile, then the antipsychotic presets.

</td>
</tr>
</table>

The full-resolution AV1 videos sit in [`docs/videos/`](docs/videos/); they are recorded by [`tools/demos/`](tools/demos/README.md).

## FAQ

- [What kind of information is inside?](#what-kind-of-information-is-inside)
- [Who made neurarium?](#who-made-neurarium)
- [Why did you make it?](#why-did-you-make-it)
- [Is it free?](#is-it-free)
- [How does the sourcing work?](#how-does-the-sourcing-work)
- [What are the sources?](#what-are-the-sources)
- [Can I ask an AI assistant about it?](#can-i-ask-an-ai-assistant-about-it)
- [How can I reuse the data?](#how-can-i-reuse-the-data)
- [How do I run it myself?](#how-do-i-run-it-myself)
- [What's the license, and why?](#whats-the-license-and-why)
- [What's on the roadmap?](#whats-on-the-roadmap)
- [What is it built with?](#what-is-it-built-with)
- [How do I give feedback or get in touch?](#how-do-i-give-feedback-or-get-in-touch)

<a name="what-kind-of-information-is-inside"></a>
<details>
<summary><strong>What kind of information is inside?</strong></summary>

Four layers of data on one model, all clickable:

| Layer | What you see | What you can do with it |
| --- | --- | --- |
| **Anatomy** | Cortical lobes, basal ganglia, diencephalon, limbic, and hindbrain as one procedural 3D mesh | Rotate, explode on a slider to reveal the deep nuclei, go transparent, peel away the near side, or isolate a single structure |
| **Wiring** | Neuron projections as directed arrows, colored by type (excitatory, dopaminergic, ...) or by excitatory/inhibitory sign | Click a pathway for its route, transmitter, and sources; play a named **functional circuit** as a traveling pulse |
| **Receptors & targets** | Receptors plus other molecular targets (transporters, enzymes, ion channels) | Focus one: the brain dims to the structures expressing it (scattered with glowing dots), beside its class, sign, and every drug acting on it |
| **Drugs** | Psychiatric drugs (from Stahl's *Prescriber's Guide*) alongside recreational and other psychoactive substances (LSD, MDMA, ketamine, cocaine, nicotine, ...), and open to more: a drug is just a row of sourced bindings, so any substance with published affinities can be added | Focus one: effect-colored dots (boost / block / modulate) animate over the regions it touches, beads flow along the transmitter systems it works through, and the panel shows its structure, class, bindings, and each binding's source |
| **Everything** | One search box; fully URL-addressable state | Search regions, pathways, receptors, and drugs at once; pivot from a drug to its class or from a target to every drug that hits it; share any view as a deep link |

Under the hood it is a **graph of nodes**. A *node* is any sourceable datum: a brain
region, a projection between two regions, a functional circuit, a receptor, a
receptor's expression in a given region, a drug, a single drug-to-target binding.
Nodes interlink, so a detail panel is a view of **one node plus every node linked to
it**, and you explore outward from whatever you clicked.

</details>

<a name="who-made-neurarium"></a>
<details>
<summary><strong>Who made neurarium?</strong></summary>

Initialy built in less than a week by [Olivier Cornelis](https://olicorne.org/), french developer and resident psychiatrist, with
the help of [Claude Code](https://claude.com/claude-code).

</details>

<a name="why-did-you-make-it"></a>
<details>
<summary><strong>Why did you make it?</strong></summary>

It began as a few-days demo during my medical residency, and it has kept absorbing new
kinds of data more easily than expected. The recurring frustration it answers: the
facts you need to reason about the brain are true but *scattered*, its regions in one
atlas, its wiring in another, its receptors in a table, its drugs in monographs, so you
spend your effort reconstructing the connections instead of using them. Putting them on
one map, each with a visible source grade, makes those connections the thing you look
at.

As a strong believer in the usefulness of reorganizing information as structured data, I believe this kind of interactive, source-graded viewer could be useful beyond
psychopharmacology, and I would happily build similar animations for **other medical
topics**. If you think a map like this would help your teaching or research, please
[get in touch](https://olicorne.org/en/contact).

</details>

<a name="is-it-free"></a>
<details>
<summary><strong>Is it free?</strong></summary>

Yes. It is free to use at [neurarium.olicorne.org](https://neurarium.olicorne.org),
free and open source (see [the license](#whats-the-license-and-why)), and the
underlying data is free to reuse (see [How can I reuse the data?](#how-can-i-reuse-the-data)).
No account, no tracking beyond basic anonymous usage counts, no paywall.

Frankly, that should be the norm: making people pay for knowledge slows humanity down.

</details>

<a name="how-does-the-sourcing-work"></a>
<details>
<summary><strong>How does the sourcing work?</strong></summary>

Because the dataset is large and machine-assembled, the honest question for any node is
*how do we know this?* Every source shown in a panel answers it inline with a colored
**provenance pill**. The goal is that **every node carries a source**, and the pill
makes the gaps visible. From weakest to strongest:

- **orange `NOSOURCE`:** no source or reference for that node yet.
- **grey `?` (LLM-only):** produced by a model from memory, unchecked; may be a hallucination.
- **yellow `~` (sourced):** from the cited document, but the node itself was not quote-verified.
- **green `✓` (verified):** a model extracted a quote, it was *programmatically* confirmed present in the cited source, and a second model agreed it supports the node. Highest grade available, and still model-driven.

The grade is part of the data, upgraded as each node is checked, so the coverage below
is a real count:

<!-- SOURCING_STATS:START (generated by tools/update_readme_stats.py; do not edit by hand) -->

**97% of the 10321 knowledge nodes in the dataset are sourced or verified.** A node is any sourceable datum (a region, a pathway, a receptor, a drug binding, ...). This is a programmatic count (`tools/update_readme_stats.py`, from the emitted data), not hand-typed:

```
Drug metabolising enzymes                        ██████████████████████████  100%    573/573
Receptor & target gene variants                  ██████████████████████████  100%    546/546
Wikipedia reference links                        ██████████████████████████  100%    445/445
Drug holders                                     ██████████████████████████  100%    305/305
Drug lipophilicity (XLogP3)                      ██████████████████████████  100%    286/286
Drug polar surface area                          ██████████████████████████  100%    286/286
Drug pre-prescription workup (BETA)              ██████████████████████████  100%    246/246
Drug blood-brain barrier label                   ██████████████████████████  100%    239/239
Drug first approval                              ██████████████████████████  100%    229/229
Drug metabolite bindings                         ██████████████████████████  100%    205/205
Drug formulations (release type)                 ██████████████████████████  100%    193/193
Receptor clinical effects (beta)                 ██████████████████████████  100%    178/178
Drug time-to-peak (Tmax)                         ██████████████████████████  100%    170/170
Drug therapeutic reference ranges                ██████████████████████████  100%    136/136
Drug laboratory alert levels                     ██████████████████████████  100%    130/130
Drug nomenclature (NbN)                          ██████████████████████████  100%    116/116
Drug originator                                  ██████████████████████████  100%    113/113
Clearance-speed prescribing guidance             ██████████████████████████  100%    104/104
Drug originator country                          ██████████████████████████  100%      81/81
Drug active metabolites                          ██████████████████████████  100%      71/71
Receptor release modulation (beta)               ██████████████████████████  100%      64/64
Brain-region anatomy                             ██████████████████████████  100%      57/57
Receptor system/family                           ██████████████████████████  100%      56/56
Receptor mechanism class                         ██████████████████████████  100%      56/56
Receptor relative amount per region              ██████████████████████████  100%      36/36
Drug market withdrawals                          ██████████████████████████  100%      28/28
Target classifications                           ██████████████████████████  100%      25/25
Metabolite-forming enzymes                       ██████████████████████████  100%      23/23
Target relative amount per region                ██████████████████████████  100%      21/21
Receptor availability across age and sex (beta)  ██████████████████████████  100%      21/21
Projection groups                                ██████████████████████████  100%      12/12
Drug prodrug flags                               ██████████████████████████  100%      11/11
Functional circuits                              ██████████████████████████  100%        6/6
Enzyme population variability                    ██████████████████████████  100%        5/5
Panel annotations                                ██████████████████████████  100%        4/4
Target tone polarity                             ██████████████████████████  100%        2/2
Drug salt / combination constituents             ██████████████████████████  100%        1/1
Drug brand names                                 ██████████████████████████  100%    575/577
Neuron pathways                                  ██████████████████████████   99%    115/116
Drug target bindings                             ██████████████████████████   99%  1953/1971
Drug half-life (T½)                              ██████████████████████████   98%    270/275
Drug class                                       █████████████████████████░   98%    295/301
Receptor expression regions                      ████████████████████████░░   94%    360/383
Drug metabolism strength tier                    ████████████████████████░░   93%    138/148
Receptor sign (excit./inhib.)                    ████████████████████████░░   91%      51/56
Target expression regions                        ███████████████████████░░░   89%    115/129
Drug binding directions                          ██████████████████████░░░░   85%  1294/1520
Pathway transmitter                              ██████████████████████░░░░   84%     98/116
Pathway sign (excit./inhib.)                     █████████████████████░░░░░   79%      30/38
Receptor pre/postsynaptic site                   ████████████████████░░░░░░   75%      42/56
```

Separately, **measured binding affinity (PDSP Ki) covers 85% of the 1952 drug bindings**; 88 of 275 drugs carry no Ki on any binding (sourced by book quote only, or not yet sourced). A Ki is a measured value, not a grade: this tracks where one was never looked up, complementing the sourcing figure above.

Of those, **442 carry an `uncertain` badge**: the quote is confirmed present in the source, but the sentence states something broader than the claim (a rule that never names the drug, a sweep that never names the region), so pinning it to that node is an inference. The badge's tooltip lists the reasons to doubt it, each with its own source.

Besides those, **667 claims are `unknown` (∅)**: every source the dataset requires for that kind of claim was searched on a recorded date and none states it. That is a finding about the literature, not a gap, so they are left out of the % above; the search is redone within 12 months.

<!-- SOURCING_STATS:END -->

</details>

<a name="what-are-the-sources"></a>
<details>
<summary><strong>What are the sources?</strong></summary>

<!-- SOURCES_TABLE:START (generated by tools/update_readme_stats.py; do not edit by hand) -->

Every `~` and `✓` grade is checked against one of the sources below. Each is a standard, widely cited reference in its field, not a casual web page:

| Source | Field | Grades here |
| --- | --- | --- |
| [Prescriber's Guide: Stahl's Essential Psychopharmacology, 8th ed.](https://doi.org/10.1017/9781009464772) | Clinical psychopharmacology | Drug bindings, nomenclature, class |
| [Kandel, Principles of Neural Science, 6th ed.](https://search.worldcat.org/search?q=bn:9781259642234) | Neuroscience (standard textbook) | Neuron pathways, region anatomy |
| [Stahl's Essential Psychopharmacology: Neuroscientific Basis, 5th ed.](https://doi.org/10.1017/9781108975292) | Psychopharmacology (mechanisms) | Receptor & target mechanism |
| [Carlat Medication Fact Book for Psychiatric Practice, 7th ed.](https://search.worldcat.org/search?q=bn:9798987335482) | Clinical psychopharmacology | Drug bindings (cross-check) |
| [Nieuwenhuys, Voogd & van Huijzen, The Human Central Nervous System, 4th ed.](https://doi.org/10.1007/978-3-540-34686-9) | Neuroanatomy (CNS atlas) | Region anatomy, connectivity |
| [IUPHAR/BPS Guide to Pharmacology (GtoPdb), tissue distribution](https://www.guidetopharmacology.org/) | Molecular pharmacology (IUPHAR/BPS database) | Receptor & target expression regions |
| [PDSP Ki Database (NIMH PDSP)](https://pdspdb.unc.edu/databases/kidb.php) | Receptor binding pharmacology | Drug binding affinities (Ki) |
| [Allen Human Brain Atlas, microarray (Hawrylycz et al. 2012)](https://human.brain-map.org/) | Brain transcriptome atlas (microarray) | Receptor & target expression regions |
| [Wikipedia (English), drug article (pharmacology sections)](https://en.wikipedia.org/) | Encyclopedia (pharmacodynamics tables) | Drug binding affinities (Ki) |
| [Wikipedia (French), drug article (commercial names)](https://fr.wikipedia.org/) | Encyclopedia (French, article prose) | Drug brand names (European / French) |
| [IUPHAR/BPS Guide to Pharmacology (GtoPdb), ligand interactions](https://www.guidetopharmacology.org/) | Molecular pharmacology (IUPHAR/BPS database) | Drug binding affinities (Ki) and direction |
| [IUPHAR/BPS Guide to Pharmacology (GtoPdb), target classification](https://www.guidetopharmacology.org/) | Molecular pharmacology (IUPHAR/BPS database) | Receptor & target mechanism class, receptor sign |
| [IUPHAR/BPS Guide to Pharmacology (GtoPdb), target function](https://www.guidetopharmacology.org/) | Molecular pharmacology (IUPHAR/BPS database) | Receptor & target physiological effects |
| [PharmFreq, metabolizer status by population](https://pharmfreq.com) | Pharmacogenomic allele frequencies | Enzyme clearance speed by population |
| [DailyMed (U.S. NLM), prescribing label, clinical pharmacology](https://dailymed.nlm.nih.gov/) | US prescribing labels (NLM SPL archive) | Drug time-to-peak (Tmax) |
| [Base de données publique des médicaments (ANSM), RCP](https://base-donnees-publique.medicaments.gouv.fr/) | French public drug database (ANSM RCPs) | Drug Tmax, half-life, French brands |
| [Base de données publique des médicaments (ANSM) or EMA EPAR, RCP sections 4.2-4.4](https://base-donnees-publique.medicaments.gouv.fr/) | French drug database (BDPM) or EMA EPAR, RCP sections 4.2-4.4 | Drug pre-prescription workup (tests before and during treatment) |
| [CPIC, clinical pharmacogenetics dosing guideline](https://cpicpgx.org/) | Pharmacogenomic prescribing guidelines | What a clearance speed implies for a drug |
| [Europe PMC, journal article](https://europepmc.org/) | Primary literature (Europe PMC abstracts) | Claims only a study measures (e.g. brain half-life) |
| [Drugs@FDA (U.S. FDA), approved application history](https://www.accessdata.fda.gov/scripts/cder/daf/) | US regulator register (Drugs@FDA) | First US approval, where no other source dates one |
| [ClinPGx (PharmGKB), clinical annotation](https://www.clinpgx.org/) | Pharmacogenomic annotations (ClinPGx) | Receptor & target gene variant associations |
| [PubChem (NCBI), computed compound properties](https://pubchem.ncbi.nlm.nih.gov/) | Chemistry database (PubChem computed properties) | Drug lipophilicity (XLogP3), polar surface area |
| [B3DB, blood-brain barrier permeability database](https://github.com/theochem/B3DB) | Blood-brain barrier database (B3DB) | Drug brain entry (BBB+ / BBB-, logBB) |
| [AGNP Consensus Guidelines for TDM in Neuropsychopharmacology, 2026](https://doi.org/10.1055/a-2860-7861) | Consensus guideline (AGNP TDM, 2026) | Therapeutic range, alert level, CYP substrate cross-check |

Some sources ask that any reuse of their data cite them:

- Harding SD, Armstrong JF, Faccenda E, Southan C, Alexander SPH, Davenport AP, Spedding M, Davies JA. The IUPHAR/BPS Guide to PHARMACOLOGY in 2026. Nucleic Acids Res. 2026;54(D1):D1446-D1456. doi:10.1093/nar/gkaf1067. PMID 41160876.
- Alexander SPH, Davenport AP, Kelly E, et al. The Concise Guide to PHARMACOLOGY 2025/26: G protein-coupled receptors. Br J Pharmacol. 2025;182:S24-S151 (and the matching 2025/26 chapter for each other target family).
- IUPHAR/BPS Guide to PHARMACOLOGY content licensed under CC BY-SA 4.0 (database ODbL).

<!-- SOURCES_TABLE:END -->

**Wikipedia** sits outside the table above. The drug and structure descriptions and the
molecule images are fetched live from the current Wikipedia article at runtime (under
[CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/)), so the dataset ships no
copyrighted prose. A live fetch is a verbatim, programmatic read that cannot drift from
the source, so in the app these carry a green `✓` pill; they are tallied as reference
links (the "Wikipedia reference links" row in the coverage above), kept separate from
the knowledge-node total.

The book references are copyrighted, so only the tooling that uses them is committed,
not the text. Anyone holding a copy can reproduce the extraction and confirm every
`✓`-graded quote: drop the Stahl PDF into `data_sources/books/stahl/` and three
committed scripts rebuild exactly what the gate checks against:

```sh
uv run tools/fetch/pdf_to_pages.py    # the PDF -> one Markdown file per page
uv run tools/fetch/build_index.py     # the per-drug page index
python tools/check_data.py            # re-verifies every quote is on its cited page
```

</details>

<a name="can-i-ask-an-ai-assistant-about-it"></a>
<details>
<summary><strong>Can I ask an AI assistant about it?</strong></summary>

Yes, neurarium is AI-ready. Paste this link once into Claude, ChatGPT, Mistral's Le Chat, Gemini or any assistant that can read web pages, and ask it to remember the site:

```
https://neurarium.olicorne.org/llms.txt
```

That page tells the assistant where the whole dataset lives and how to read it, including a plain-text version of every panel at [`/api/`](https://neurarium.olicorne.org/api/) (one page per drug, receptor, region and pathway). From then on you can ask it things like "according to neurarium, what does aripiprazole bind, and how well sourced is each binding?" and it can quote the exact source sentence and grade behind each answer instead of answering from memory. Whether it keeps the link across conversations depends on the assistant's own memory feature; if it forgets, paste the link again.

The assistant only reads what neurarium states, so the work-in-progress warning above still applies. The text version also holds slightly less than the viewer: the sections the viewer computes in your browser from the stored facts (a drug's predicted effects and presynaptic modulation, its net neurotransmission estimate, its pharmacokinetic interactions, the simulation) are only in the 3D version.

**Why no MCP server?** The [Model Context Protocol](https://en.wikipedia.org/wiki/Model_Context_Protocol) is the other common way to plug a site into an AI assistant, but it needs a server program running next to the site, a connector that each user has to add by hand, and ongoing upkeep as the protocol evolves. I decided against it: neurarium follows the [`/llms.txt`](https://llmstxt.org) convention instead, plain files that any assistant able to read a web page can use with nothing to install, and that cost the server nothing extra.

</details>

<a name="how-can-i-reuse-the-data"></a>
<details>
<summary><strong>How can I reuse the data?</strong></summary>

The anatomy is plain **structured data**, kept deliberately separate from the
rendering. Under `public/data/` it is split by node kind (one JSON object per line)
beside a self-describing `meta.json` (colour and legend maps plus the sourcing tally)
and one geometry file per shape. It is generated from a single source of truth
(`tools/generate_data.py`, with the drug list in `tools/data/drugs_data.jsonl`), so the
plain JSONL/JSON is easy to consume from another engine.

| File | What it holds |
| --- | --- |
| [`structures.jsonl`](public/data/structures.jsonl) | Brain regions (position, group, geometry ref, sources) |
| [`projections.jsonl`](public/data/projections.jsonl) | Neuron pathways (from -> to, transmitter, sign, sources) |
| [`circuits.jsonl`](public/data/circuits.jsonl) | Named functional circuits |
| [`projection_groups.jsonl`](public/data/projection_groups.jsonl) | By-transmitter / by-effect pathway groups |
| [`receptors.jsonl`](public/data/receptors.jsonl) | Receptors: classification + expression regions, each graded |
| [`drugs.jsonl`](public/data/drugs.jsonl) | Drugs: bindings (target, action, Ki), class, nomenclature |

Each row of every file carries its own provenance grade and source, so the graph stays
self-describing. For how to extend the dataset, the per-tool reference, and the
emitted-data field contract, see [`tools/README.md`](tools/README.md). The data is under
the same [license](#whats-the-license-and-why) as the code.

The same open data files also make it easy to build other tools on top of neurarium. [DrugsMap](public/drugs-map/README.md) is there as an example of how to reuse neurarium's data: a standalone page that places every drug by a PCA of its binding profile, built on those files alone, so its code shows how to load and use them (live at [drugsmap.olicorne.org](https://drugsmap.olicorne.org/)).

</details>

<a name="how-do-i-run-it-myself"></a>
<details>
<summary><strong>How do I run it myself?</strong></summary>

The page loads its data with `fetch()`, so it must be served over HTTP (not opened from
disk). The served site is `public/`. From the repository root:

```sh
python tools/serve.py            # serves public/ with caching disabled
# or: cd public && python -m http.server 8000
```

Then open <http://localhost:8000/>.

For deployment there is a hardened [Caddy](https://caddyserver.com/) container under
`docker/`; the full data flow and module graph are in
[`ARCHITECTURE.md`](docs/ARCHITECTURE.md).

</details>

<a name="whats-the-license-and-why"></a>
<details>
<summary><strong>What's the license, and why?</strong></summary>

[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE).

I chose a strong copyleft license on purpose: anyone is free to use, study, modify, and
build on neurarium, but any reuse or hosting of it (including a modified version run as
a website) must keep its source open under the same terms. The point is to keep the
work and its data freely available and prevent it from being closed off into a
proprietary fork.
Drug descriptions and molecular-structure images come from Wikipedia, used under [CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/).

</details>

<a name="whats-on-the-roadmap"></a>
<details>
<summary><strong>What's on the roadmap?</strong></summary>

A sample of the planned directions, none fixed in order: **more animation** of activity
and signal flow across the brain; **more substances** with their commercial brand
names; **pathologies** mapped onto regions, circuits, and transmitter systems; **deeper
pharmacology** (CYP enzymatic interactions, second-order receptor effects);
**consistency checks** that flag self-contradicting data; and **toward full sourcing**,
lifting every node's grade from grey toward green as it is checked.

</details>

<a name="what-is-it-built-with"></a>
<details>
<summary><strong>What is it built with?</strong></summary>

Deliberately lightweight, with a small attack surface and no build step:

- **Frontend:** vanilla ES modules + [three.js](https://threejs.org/) loaded via an
  import map and vendored under `public/vendor/three`, so the page runs no third-party
  script at runtime and works offline. No framework, bundler, or `node_modules`.
- **Data:** `tools/generate_data.py` (Python standard library only) emits the anatomy
  as `public/data/` (`meta.json` + `*.jsonl` + `shapes/*.json`), fetched at runtime.
- **Serving:** a hardened [Caddy](https://caddyserver.com/) container (non-root,
  read-only rootfs, dropped capabilities, resource limits, strict Content-Security-
  Policy) behind a TLS-terminating reverse proxy.
- **Debugging:** an [eruda](https://github.com/liriliri/eruda) on-screen console,
  loaded only in dev or with `?debug` so it never ships to normal visitors.

For the viewer's file-by-file map and the non-obvious rules, see
[`CLAUDE.md`](CLAUDE.md).

</details>

<a name="how-do-i-give-feedback-or-get-in-touch"></a>
<details>
<summary><strong>How do I give feedback or get in touch?</strong></summary>

Found a bug, an anatomical or pharmacological **inaccuracy**, or have a **feature
request**? Please **open an issue** on this repository. Corrections to the regions,
projections, receptor, and drug data are especially welcome, as are **ideas for what
else belongs on a map like this**.

For anything else, or to talk about a similar viewer for another medical topic, you can
reach me on [my website](https://olicorne.org/en/contact).

</details>
