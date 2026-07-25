#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "beautifulsoup4>=4.12",
# ]
# ///
"""Build a Wikipedia binding worklist for a drug's active *metabolites*.

Why this exists
---------------
Each drug in ``tools/data/drugs_data.jsonl`` may carry active ``metabolites`` (see
CLAUDE.md "Drugs" -> "Half-life + active metabolites"). Five of them are themselves
modeled drugs (``drug_id`` link) and reuse that drug's bindings; the rest carried a
name + half-life only, their receptor bindings deferred to this pass. This script is
that pass: for every *non-modeled* metabolite it mines the English Wikipedia for a
binding profile, exactly like the drug-level corpus #9 (``wikipedia_pharm``) pass.

It deliberately REUSES ``fetch_wikipedia_pharmacology`` as a library (page fetch +
store, table Ki extraction, target-name resolution) rather than duplicating any of it,
and writes into the SAME corpus #9 store (``data_sources/wikipedia/{raw,pages}/``) so a
metabolite's quote gates against ``pages/<slug>.md`` identically to a drug's.

What it does
------------
For each non-modeled metabolite:

1. Resolve a Wikipedia page title (an explicit ``TITLE_OVERRIDES`` entry, else the
   metabolite name). ``fetch_page`` follows redirects, so the *real* returned title is
   recorded. A metabolite with no distinct article usually redirects to its parent drug
   (or another drug); that is detected (``redirected_to``) and its Ki TABLE is NOT
   harvested, because the parent's affinity table describes the *parent*, not the
   metabolite (mis-attribution guard). Prose action sentences are still collected: they
   name the metabolite explicitly, so a sentence that mentions it is safe to quote.
2. Fetch + store the page into corpus #9 (skipped when already stored and not
   ``--refresh``).
3. Extract, from a metabolite's OWN article only, the Ki-table bindings
   (``extract_bindings``); and, from any article, the candidate *action* sentences
   (paragraph lines naming an action verb), verbatim from the stored page text so a
   judge's quote gates cleanly.
4. Write ``tools/generated_cache/metabolite_bindings_worklist.json`` for a single LLM
   pass (see CLAUDE.md) that assigns each binding a target + action (or affinity-only),
   consumed by ``tools/sourcing/apply_metabolite_bindings.py``.

Usage (from the repo root; network unless ``--no-fetch``)::

    uv run tools/fetch/fetch_metabolite_bindings.py           # fetch missing + build worklist
    uv run tools/fetch/fetch_metabolite_bindings.py --refresh  # re-fetch every page
    uv run tools/fetch/fetch_metabolite_bindings.py --no-fetch # re-parse stored pages only
    uv run tools/fetch/fetch_metabolite_bindings.py --only norquetiapine,mcpp

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)          # sibling fetch_wikipedia_pharmacology.py + fetch_ki.py
import fetch_wikipedia_pharmacology as wp  # noqa: E402  (reuse fetch/store/extract; no dup)
import fetch_ki as ki  # noqa: E402  (PDSP Ki: discover a metabolite's measured targets, corpus #5)
import drugs_io  # noqa: E402

WORKLIST = os.path.join(REPO, "tools", "generated_cache",
                        "metabolite_bindings_worklist.json")

# Metabolites that have their OWN distinct Wikipedia article (the whole page is about
# the metabolite, so its Ki table and every action sentence describe it). Keyed by the
# lowercased metabolite name -> the confirmed article title. This is an ALLOW-LIST on
# purpose: only a confirmed own-article page is Ki-harvested, so a metabolite whose name
# happens to resolve to an unrelated or parent page (e.g. "M-II" -> a videocassette
# format, "Norfluoxetine" -> its enantiomer article) can never contribute mis-attributed
# bindings. Every other metabolite falls back to its PARENT article for action sentences
# only, filtered to lines that actually name the metabolite (see fetch loop).
OWN_ARTICLE = {
    "7-hydroxyamoxapine": "7-Hydroxyamoxapine",
    "8-hydroxyamoxapine": "8-Hydroxyamoxapine",
    "6-hydroxybupropion": "Hydroxybupropion",
    "desmethylclomipramine": "Norclomipramine",
    "norfluoxetine": "Seproxetine",   # WP article for (S)-norfluoxetine, an SSRI like it
    "meta-chlorophenylpiperazine": "meta-Chlorophenylpiperazine",
    "licarbazepine": "Licarbazepine",
    "norquetiapine": "Norquetiapine",
    "desmethylselegiline": "Desmethylselegiline",
    "l-amphetamine": "Levoamphetamine",
    "l-methamphetamine": "Levomethamphetamine",
    "(+)-alpha-dihydrotetrabenazine": "Dihydrotetrabenazine",
    "o-desmethylvenlafaxine": "Desvenlafaxine",
    "diethyldithiocarbamate": "Sodium diethyldithiocarbamate",
    "carbon disulfide": "Carbon disulfide",
}

# Action verbs that mark a paragraph line as a candidate for sourcing a binding's
# functional direction. A line naming one of these AND (ideally) a receptor is worth
# handing to the judge. Broad on purpose; the judge + quote gate are the real filter.
ACTION_RE = re.compile(
    r"\b(agonist|antagonist|inhibitor|inhibits?|inhibition|reuptake|"
    r"releaser|releases?|partial agonist|inverse agonist|blocker|blocks?|"
    r"modulator|antagonism|agonism|affinity|binds?|potent)\b", re.I)
# A receptor/target-ish token in a line, so we prefer lines that actually name a site
# (a bare "potent inhibitor" with no target is useless to the judge).
TARGET_HINT_RE = re.compile(
    r"\b(5-?HT|receptor|transporter|SERT|NET|DAT|adrenerg|dopamin|serotonin|"
    r"histamin|muscarinic|H1|H2|D[1-5]\b|M[1-5]\b|alpha|beta|α|β|MAO|"
    r"NMDA|sigma|opioid|GABA|nicotinic|cholinerg)\b", re.I)

MAX_ACTION_LINES = 14   # cap candidate lines per metabolite (keeps the worklist compact)


def non_modeled_metabolites(drugs: list[dict]) -> list[dict]:
    """Every metabolite that is not itself a modeled drug, deduped by identity.

    Mirrors ``js/data.js``: a metabolite links to a modeled drug by explicit
    ``drug_id`` or by its name matching a drug id, and those reuse that drug's
    bindings (nothing to source here). The rest are returned as
    ``{name, parents, key}`` (``key`` = a stable lowercase id for --only / worklist).

    A single metabolite can be produced by more than one modeled drug (e.g. mCPP by
    nefazodone AND trazodone). Its bindings are a property of the molecule, not of the
    parent relationship, so it is sourced ONCE: we key by ``wp.slugify(name).lower()``
    and collect every parent into ``parents``. The applier then writes that one judged
    binding list identically under each parent (check_data guards they stay identical),
    and the tally + viewer dedup the same way -- so a shared metabolite is never
    double-counted or double-listed."""
    drug_ids = {d["id"] for d in drugs}
    by_norm = {}
    for d in drugs:
        by_norm[re.sub(r"[^a-z0-9]+", "", d.get("name", "").lower())] = d["id"]
    by_key: dict[str, dict] = {}
    for d in drugs:
        for m in d.get("metabolites", []):
            name = m["name"]
            linked = m.get("drug_id") or by_norm.get(
                re.sub(r"[^a-z0-9]+", "", name.lower()))
            if linked and linked in drug_ids:
                continue
            key = wp.slugify(name).lower()
            entry = by_key.get(key)
            if entry:
                if d["id"] not in entry["parents"]:
                    entry["parents"].append(d["id"])
            else:
                by_key[key] = {"name": name, "parents": [d["id"]], "key": key}
    return list(by_key.values())


def _norm(s: str) -> str:
    """Lowercase + drop every non-alphanumeric, so a metabolite name matches its
    mention regardless of hyphens/spaces/commas (Carbamazepine-10,11-epoxide)."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def action_lines(page_text: str, must_mention: str | None = None) -> list[str]:
    """Paragraph lines from the stored page text that name an action verb + a target
    hint, verbatim (so a judge's quote taken from one gates against pages/<slug>.md).

    Only prose lines ('- ' list items or plain paragraphs) are considered, never table
    rows (those are the Ki source) or headings. Deduplicated, capped.

    ``must_mention`` (a metabolite name) restricts to lines that actually name it, used
    when the page is the PARENT article (a fallback): a parent-only sentence must never
    be quoted for the metabolite, only a sentence that explicitly discusses it."""
    mention = _norm(must_mention) if must_mention else None
    seen, out = set(), []
    for raw in page_text.splitlines():
        line = raw.strip()
        # Only real prose paragraphs: skip headings, flattened table rows, and '- ' list
        # items (Wikipedia navbox/"See also" enumerations render as <li>, and their long
        # comma lists of drug names carry action verbs but say nothing about THIS
        # compound). The binding facts we want live in the lead + Pharmacology <p>.
        if not line or line.startswith(("#", "- ")) or " | " in line:
            continue
        if not (ACTION_RE.search(line) and TARGET_HINT_RE.search(line)):
            continue
        if line.count(",") > 5:
            continue  # an enumeration (a navbox caption that slipped in as a <p>)
        # Require real sentence punctuation: a navbox caption / list header ("Serotonin
        # reuptake inhibitors: Atomoxetine ...", "See also: ...") is a run of names with
        # no sentence period, whereas a binding claim is prose ("mCPP is ... at 5-HT2C.").
        if not (line.endswith(".") or ". " in line):
            continue
        if line.lower().startswith("see also"):
            continue
        if mention and mention not in _norm(line):
            continue
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
        if len(out) >= MAX_ACTION_LINES:
            break
    return out


def parent_titles(drugs: list[dict]) -> dict[str, str]:
    """Parent drug id -> its Wikipedia article title (leaf of its wikipedia url, else
    its name), so a metabolite page that redirected to its parent can be detected."""
    out = {}
    for d in drugs:
        url = d.get("wikipedia") or ""
        if "/wiki/" in url:
            import urllib.parse
            out[d["id"]] = urllib.parse.unquote(url.rsplit("/wiki/", 1)[1]).replace("_", " ")
        else:
            out[d["id"]] = d.get("name") or d["id"]
    return out


def load_page(title: str, no_fetch: bool, refresh: bool):
    """Load one Wikipedia article's stored text (fetching + storing it if allowed and not
    already cached), reusing the corpus #9 raw/pages store so a quote taken from the
    returned text gates against ``pages/<slug>.md``.

    Returns ``(found, real_title, slug, page_text, soup)``; ``found`` is False (and the
    rest best-effort) when the page is neither stored nor fetchable."""
    slug = wp.slugify(title)
    raw_path = os.path.join(wp.RAW_DIR, f"{slug}.html")
    if no_fetch or (os.path.exists(raw_path) and not refresh):
        if not os.path.exists(raw_path):
            return (False, title, slug, "", None)
        html = open(raw_path, encoding="utf-8").read()
        # The real (post-redirect) title is stamped into the stored comment header.
        hm = re.search(r"<!--\s*(.+?)\s*-->", html[:200])
        real_title = hm.group(1) if hm else title
    else:
        try:
            page = wp.fetch_page(title)
        except SystemExit:
            return (False, title, slug, "", None)
        soup0 = BeautifulSoup(page["html"], "html.parser")
        wp.store_page(page, wp.render_page_text(soup0))
        html = f"<!-- {page['title']} -->\n{page['html']}"
        real_title = page["title"]
        slug = wp.slugify(real_title)   # store_page slugs on the real title
    soup = BeautifulSoup(html, "html.parser")
    page_md = os.path.join(wp.PAGES_DIR, f"{slug}.md")
    page_text = open(page_md, encoding="utf-8").read() if os.path.exists(page_md) else ""
    return (True, real_title, slug, page_text, soup)


def pdsp_targets(name: str) -> list[dict]:
    """Every modeled target for which the PDSP Ki database (corpus #5) has an ACTIVE
    (sub-10 uM) assay measured on this metabolite's OWN name -> ``[{target, ki_id,
    value_nm}]`` for a representative assay.

    This makes PDSP a target-DISCOVERY source, not merely a Ki upgrade for a
    Wikipedia-found target as before: a metabolite absent from Wikipedia's binding table
    but present in PDSP (norfluoxetine: 40 assays across 15 sites) still gets its measured
    bindings. The applier turns each into an ``affinity_only`` binding (a measured Ki, no
    functional direction); the judge may still attach an action from prose."""
    try:
        rows, _ = ki.resolve_rows(name, None)
    except Exception:
        return []
    out = []
    for tid in sorted({ki.resolve_target(r) for r in rows} - {None}):
        s = ki.summarize_target(rows, tid)
        if s and s.get("ki_nm"):   # has an active tier (not inactive-/qualified-only)
            out.append({"target": tid, "ki_id": s["source"]["ki_id"],
                        "value_nm": s["source"]["value_nm"]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true",
                    help="re-fetch every page even if already stored")
    ap.add_argument("--no-fetch", action="store_true",
                    help="re-parse stored pages only (no network)")
    ap.add_argument("--only", default="",
                    help="comma-separated metabolite keys to limit to")
    args = ap.parse_args()

    drugs = drugs_io.load_drugs()
    valid_ids = wp.load_valid_ids()
    ptitles = parent_titles(drugs)
    metabs = non_modeled_metabolites(drugs)
    if args.only:
        want = {k.strip().lower() for k in args.only.split(",") if k.strip()}
        metabs = [m for m in metabs if m["key"] in want]

    worklist = []
    for m in metabs:
        own = m["name"].lower() in OWN_ARTICLE
        parent_title = ptitles.get(m["parents"][0], "")
        # Pages to mine for ACTION prose, each tagged whether it is the metabolite's OWN
        # article (every sentence describes it -> unfiltered) or the PARENT article (only
        # sentences that explicitly name the metabolite -> the mis-attribution guard).
        # #3 relaxation: an own-article metabolite ALSO draws on its parent's prose,
        # because a thin own article (Seproxetine for norfluoxetine) routinely omits the
        # binding profile that the parent article (Fluoxetine) states about the
        # metabolite. A parent-fallback metabolite reads only the parent, as before.
        to_read: list[tuple[str, bool]] = []
        if own:
            to_read.append((OWN_ARTICLE[m["name"].lower()], True))
        if parent_title:
            to_read.append((parent_title, False))
        if not to_read:                      # neither an own nor a parent article known
            to_read.append((m["name"], False))

        entry = {"metabolite": m["name"], "parents": m["parents"], "key": m["key"],
                 "wiki_title": "", "slug": "", "own_article": own, "found": False,
                 "from_parent": not own, "ki_bindings": [], "unresolved_ki": [],
                 "action_candidates": [], "pages": [],
                 # PDSP target discovery (corpus #5), keyed by the metabolite's own name.
                 "pdsp_targets": pdsp_targets(m["name"])}

        seen_lines: set[str] = set()
        for title, is_own in to_read:
            found, real_title, slug, page_text, soup = load_page(
                title, args.no_fetch, args.refresh)
            if not found:
                continue
            entry["found"] = True
            if not entry["slug"]:            # primary page = first one successfully read
                entry["slug"] = slug
                entry["wiki_title"] = real_title
            if slug not in entry["pages"]:   # a judged quote may gate against ANY read page
                entry["pages"].append(slug)
            for line in action_lines(page_text,
                                     must_mention=None if is_own else m["name"]):
                if line not in seen_lines:
                    seen_lines.add(line)
                    entry["action_candidates"].append(line)
            # The Ki table is harvested ONLY from a confirmed own article (a parent's table
            # is the parent's affinities, never the metabolite's).
            if is_own and soup is not None:
                res = wp.extract_bindings(soup, valid_ids)
                for tid, b in res["bindings"].items():
                    entry["ki_bindings"].append({
                        "target": tid, "wiki_name": b["wiki_name"],
                        "ki": b["ki"], "quote": b["quote"]})
                entry["unresolved_ki"] = res["unresolved"]

        entry["action_candidates"] = entry["action_candidates"][:MAX_ACTION_LINES]
        if not entry["found"]:
            print(f"  - {m['name']}: no page found (run without --no-fetch to fetch)")
        n_ki = len(entry["ki_bindings"])
        n_act = len(entry["action_candidates"])
        n_pdsp = len(entry["pdsp_targets"])
        print(f"  - {m['name']} [{entry['wiki_title'] or '?'}]: {n_ki} Ki rows, "
              f"{n_act} action lines, {n_pdsp} PDSP targets, pages={entry['pages']}")
        worklist.append(entry)

    os.makedirs(os.path.dirname(WORKLIST), exist_ok=True)
    with open(WORKLIST, "w", encoding="utf-8") as f:
        json.dump(worklist, f, ensure_ascii=False, indent=2)
        f.write("\n")
    n_found = sum(1 for e in worklist if e["found"])
    n_ki = sum(len(e["ki_bindings"]) for e in worklist)
    n_act = sum(len(e["action_candidates"]) for e in worklist)
    n_pdsp = sum(len(e["pdsp_targets"]) for e in worklist)
    print(f"\nwrote {WORKLIST}")
    print(f"  {len(worklist)} metabolites, {n_found} pages found, "
          f"{n_ki} Ki-table rows, {n_act} action candidate lines, "
          f"{n_pdsp} PDSP-discovered targets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
