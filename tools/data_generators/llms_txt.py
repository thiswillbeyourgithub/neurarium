"""``public/llms.txt``: the site explained to an LLM agent (https://llmstxt.org).

The viewer is a WebGL canvas an agent cannot read, but everything it shows comes from the
static files under ``public/data/``. This page points an agent at those files instead of a
crawl, and steers bulk use to the GitHub clone. Generated from the emitted records so the
file list, record counts and field names never drift from the data; the prose is English
only (the audience is a model, not a visitor).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

SITE_URL = "https://neurarium.olicorne.org"
REPO_URL = "https://github.com/thiswillbeyourgithub/neurarium"
CONTACT_URL = "https://olicorne.org/en/contact"

# One line per emitted collection (in claim_walk.COLLECTIONS order): what a record is. A collection missing here raises, so a
# new one cannot ship undescribed.
COLLECTION_BLURBS: dict[str, str] = {
    "structures": "brain regions (id, name, group, position, aliases, sources). Paired regions are emitted once on the right (`mirror: true`); the left twin is implied",
    "projections": "pathways between regions (from, to, kind, transmitter/sign claims, sources)",
    "circuits": "named circuits (a set of regions; member pathways are the projections with both ends in the set)",
    "projection_groups": "projection groups by kind or sign (members are the projections matching it)",
    "receptors": "neurotransmitter receptors (family, class, sign, synaptic site, expression regions + density, effects, variants), each attribute graded separately",
    "drugs": "CNS-active drugs (bindings with action + Ki, categories, brands, half-life, Tmax, enzymes, metabolites, pharmacogenomics, formulations, regulatory history, originator company + its country, current marketing-authorisation holders, computed lipophilicity XLogP3 + topological polar surface area in Å² (PubChem), curated blood-brain-barrier label BBB+/BBB- + measured logBB (B3DB), BETA `workup[]`: the checks the French label (RCP sections 4.2-4.4, BDPM) asks for, one `{test, timing, conditions?}` per node, `timing` = `before` starting or `during` treatment, `conditions` (French, verbatim from the label) present when the label asks for it only in some patients, labels in meta `workup_tests` / `workup_timings`)",
    "metabolites": "active metabolites, one record per molecule (`drug_id`, half-life, own bindings), referenced from a drug's `metabolites[]`",
    "addons": "annotations attached to one panel (`owner_kind`, `owner`, `slot`), e.g. a caveat on one drug",
}

_VERSION_RE = re.compile(r"""__APP_VERSION__\s*=\s*["']([^"']+)["']""")


def app_version(root: Path) -> str:
    """The release string from ``public/version.js``, the single source of the version."""
    match = _VERSION_RE.search((root / "version.js").read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"{root / 'version.js'}: no __APP_VERSION__ assignment")
    return match.group(1)


def _fields(records: list[dict[str, Any]]) -> list[str]:
    """Every top-level key any record carries, in first-seen order."""
    seen: dict[str, None] = {}
    for record in records:
        seen.update(dict.fromkeys(record))
    return list(seen)


def render(version: str, collections: dict[str, list[dict[str, Any]]], meta_keys: list[str],
           n_quotes: int, effect_lines: list[str] | None = None) -> str:
    """The llms.txt Markdown for these emitted collections. ``effect_lines`` is the BETA
    effect index (``effect_index.summary_lines``), its own section when given."""
    unknown = set(collections) - set(COLLECTION_BLURBS)
    if unknown:
        raise KeyError(f"llms_txt.COLLECTION_BLURBS has no entry for {sorted(unknown)}")
    data_lines = []
    for name, records in collections.items():
        fields = ", ".join(f"`{f}`" for f in _fields(records))
        data_lines.append(f"- [{name}.jsonl]({SITE_URL}/data/{name}.jsonl): {len(records)} "
                          f"{COLLECTION_BLURBS[name]}. Fields: {fields}")
    meta = ", ".join(f"`{k}`" for k in meta_keys)
    effects = "" if not effect_lines else f"""
## Clinical effects (BETA, derived)

Each effect below is one a source attributes to acting on a receptor in some mode (the receptors' stored `effects[]` nodes), with the drugs whose directional bindings could produce it. The drug side is derived, never stored, and not medical advice: a drug listed does not necessarily cause it. Full list per effect, with sources and the bindings that lead there: `{SITE_URL}/api/effect/<id>` (also listed at `/api/effect/`); viewer: `{SITE_URL}/#tabs=effect:<id>`. A receptor with no `effects[]` but an `effects_unknown` stamp was searched and no source states an effect for it; it is listed under no effect.

{chr(10).join(effect_lines)}
"""
    return f"""# Neurarium

> An interactive 3D brain visualizer with an open dataset of brain regions, pathways, neurotransmitter receptors and CNS drugs (bindings, pharmacokinetics, metabolism, pharmacogenomics). Every claim is a "node" carrying its own source quote and a provenance grade. Version {version}. Not medical advice.

## Please do not crawl or index this site

The site is a single page; everything it shows is already in the public repository, so crawling it only loads a small server. To read or analyse the data in bulk, clone the repository instead:

```
git clone {REPO_URL}
```

The data is under `public/data/`. For a handful of lookups, fetching the individual files listed below is fine.

## The code is documented

The whole codebase (viewer, data generator, sourcing pipeline, deploy) is documented in the repository. It was written with the help of Claude Code, and the docs are written to be read by an agent:

- [CLAUDE.md]({REPO_URL}/blob/main/CLAUDE.md): the map of the repository and its non-obvious rules; start here
- [docs/ARCHITECTURE.md]({REPO_URL}/blob/main/docs/ARCHITECTURE.md): the node model, data flow, module graph
- [docs/PROVENANCE.md]({REPO_URL}/blob/main/docs/PROVENANCE.md): sources, grades, how a quote is verified
- [docs/DRUGS.md]({REPO_URL}/blob/main/docs/DRUGS.md): the drug dataset and how each field is sourced
- [tools/README.md]({REPO_URL}/blob/main/tools/README.md): how the data is generated, checked and refreshed

## Readable pages (start here for a lookup)

[{SITE_URL}/api/]({SITE_URL}/api/) is the dataset as Markdown, one page per node (e.g. `{SITE_URL}/api/drug/sertraline`, `{SITE_URL}/api/receptor/d2`), all listed at `/api/` (one kind: `/api/drug/`). An address with no page returns the full list with ids (status 404), so a guessed id is one step from the right one. Each page opens with a legend of the grades, then holds the node's stored fields, each claim tagged `[grade quote_id]` on its own line, with the verbatim quotes and their source links listed under Sources at the end. A claim graded `llm` is flagged UNSOURCED: an LLM wrote it from memory and no document backs it, so never cite it as sourced. A long page lists its sections at the top, each also served alone (e.g. `{SITE_URL}/api/drug/sertraline/bindings`, with only the sources that section cites).

**The human version shows slightly more.** The 3D viewer also computes a few sections in the browser from these stored facts, and apart from the BETA effect index (below) they are deliberately not on the text pages: a drug's predicted effects and presynaptic modulation (from its bindings and each receptor's effects), its net neurotransmission estimate, its pharmacokinetic interactions (from shared metabolic enzymes), and the simulation. Each is a combination of claims that are on the pages, so an agent can reason them out itself, but it should say so rather than present them as neurarium's statement, and point its user to the viewer link on each page to see them.
{effects}
## Data files

Static JSON Lines (one record per line) and JSON, regenerated from the repository on every release. English only; French strings are in `translations.fr.json` (English string -> French).

{chr(10).join(data_lines)}
- [quotes.jsonl]({SITE_URL}/data/quotes.jsonl): {n_quotes} source quotes (`id`, `corpus`, `page`, `quote`, judge `llm`, `fetched` date). Records cite them by `quote_id`
- [meta.json]({SITE_URL}/data/meta.json): vocabularies and labels shared by the records ({meta})
- [changelog.json]({SITE_URL}/data/changelog.json): what changed in each release

## How to find things

- A drug, receptor or region: find its line in the matching `.jsonl` by `id` (lowercase, underscores, e.g. `sertraline`, `d2`, `putamen_R`) or by `name`.
- A claim's evidence: each claim has `sources: [{{"quote_id", "pipeline", "provenance"}}]`. Look up `quote_id` in `quotes.jsonl` for the verbatim sentence, and its `corpus` in `meta.json` `source_corpora` for the full reference. `page` is a book page or a corpus-specific id (PMID, GtoPdb target id, Wikipedia slug, DailyMed setid, ...).
- How much to trust a claim: `provenance` is `verified` (quote found on the page and confirmed by a separate LLM judge), `sourced` (document given, quote not checked) or `llm` (from model memory, unchecked). No source at all means unsourced. A non-empty `uncertainty[]` lists reasons for doubt (e.g. `isolated_tissue` on a receptor effect: every source reports only an isolated human tissue preparation, such as a vessel ring, not a whole body). An `unknown` stamp `{{searched, corpora}}` (a binding's `unknown`, a receptor's `effects_unknown`) is a finding, not a gap: every listed corpus was searched on that date and none states the claim. `meta.json` `provenance_stats` gives the totals per node kind.
- What a drug does: `drugs.jsonl` `bindings[]` gives `target` (a receptor id from `receptors.jsonl` or a target in `meta.json` `drug_targets`), `action` and, where measured, the Ki. A salt declaring `constituents` (dimenhydrinate) carries no binding of its own and acts through its constituents' records. Effects in the viewer (which regions light up, tone changes, drug interactions) are derived from these in the browser code under `public/js/`, not stored.
- Descriptions are not stored: the viewer fetches the live Wikipedia lead linked from a record's `wikipedia` field.

## Live status

- [status.json]({SITE_URL}/status.json): `{{"version", "started_at"}}`, the running release and the container start time (Unix seconds, rounded down to 5 minutes). Compare `version` with the one above to see whether this file is current.

## Linking a person to a view

Hash deep links open detail panels: `{SITE_URL}/#tabs=drug:sertraline` (kinds `drug`, `target`, `structure`, `circuit`, `group`, `enzyme`; several comma-separated, e.g. `#tabs=drug:sertraline,target:d2`).

## Feature ideas, errors, questions

Tell the developer at {CONTACT_URL}. A suggestion from an agent relaying its user is welcome, as is a report of a wrong or badly sourced claim (cite the record `id` and `quote_id`).
"""
