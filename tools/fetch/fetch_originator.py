#!/usr/bin/env python
"""Build the drug-originator worklist (kinds drug_originator / drug_originator_country).

Fetch / candidate-extraction half of the usual four-step pipeline; it states **no
verdict of its own**. Two lists, both from stored English Wikipedia articles (corpus #9
``wikipedia_pharm``, ``data_sources/wikipedia/pages/<slug>.md``):

* ``drugs``: per drug, every sentence of its article's lead and history-like sections
  (``fetch_drug_history.section_sentences``) naming who discovered / synthesized /
  developed / invented it (``origin.ORIGINATOR_RE``), indexed.
* ``companies``: per originator company article listed in :data:`COMPANY_ARTICLES`
  (hand-confirmed: the article IS that company, and the names it goes by), its infobox
  location rows (``Headquarters | ...``, ``Country | ...``) and every lead / history
  sentence that names a country (``history.COUNTRIES`` patterns) or a successor
  (``origin.SUCCESSOR_RE``: acquired, merged, renamed), indexed.

The LLM answers by index into ``originator_judged.json``;
``tools/sourcing/apply_originator.py`` gates + writes. A company article is fetched once
with ``uv run tools/fetch/fetch_wikipedia_pharmacology.py --title "<Title>"`` (it lands
in the same ``pages/`` tree with the usual revision header), then listed below.

Usage (from the repo root)::

    python tools/fetch/fetch_originator.py
    python tools/fetch/fetch_originator.py --only citalopram,cyamemazine   # merges

Stdlib only, offline; author-side (needs the gitignored ``data_sources/`` tree).

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent   # repo root
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE))
from lib.page_file import page_path  # noqa: E402 (refuses a path-like page)
from lib import drugs_io  # noqa: E402
from lib import worklist_io  # noqa: E402
from pipeline.judged import ECHO_QID  # noqa: E402
from lib.worklist_io import merge_scoped  # noqa: E402
from lib.corpora import wikipedia as wikistore  # noqa: E402 (page_for, PAGES_DIR)
import fetch_drug_history  # noqa: E402 (section_sentences)
from data_generators import history, origin  # noqa: E402

OUT_PATH = ROOT / "tools" / "generated_cache" / "originator_worklist.json"
MAX_LINE = 600
CORPUS = "wikipedia_pharm"

# Originator company article slug (pages/<slug>.md) -> the names the company goes by
# in drug articles. Hand-confirmed: the judged drug pick names a slug, and the applier
# accepts it only when the picked lab name is one of these, so a drug can never borrow
# an unrelated company's country.
COMPANY_ARTICLES: dict[str, list[str]] = {
    # Not listed: "Gedeon Richter", "Orion" and "Vivus" resolve to a person, a
    # disambiguation page and a drug; Endo Laboratories resolves to Endo International,
    # a later Irish-domiciled holding whose country is not the 1960s New York lab's.
    "abbott_laboratories": ["Abbott Laboratories"],
    "acadia_pharmaceuticals": ["Acadia Pharmaceuticals"],
    "actelion": ["Actelion Pharmaceuticals"],
    "amgen": ["Amgen Inc."],
    "angelini": ["Angelini Research Laboratories"],
    "astra_ab": ["Astra AB"],
    "beecham_group": ["Beecham"],
    "boots_company": ["Boots"],
    "bristol_myers_squibb": ["Bristol-Myers Squibb"],
    "eisai_company": ["Eisai"],
    "eli_lilly_and_company": ["Eli Lilly and Company"],
    "farmitalia": ["Farmitalia-Carlo Erba"],
    "gr_nenthal": ["Grünenthal"],
    "gsk_plc": ["GlaxoSmithKline"],
    "ig_farben": ["IG Farben"],
    "imperial_chemical_industries": ["Imperial Chemical Industries"],
    "janssen_pharmaceuticals": ["Janssen Pharmaceutica"],
    "king_pharmaceuticals": ["King Pharmaceuticals"],
    "laboratoires_servier": ["Servier Laboratories"],
    "lundbeck": ["Lundbeck"],
    "mead_johnson": ["Mead Johnson"],
    "merck_co": ["Merck"],
    "merck_group": ["Merck", "Merck KGaA"],
    # Ciba, Geigy and Ciba-Geigy redirect to Novartis, the company they merged into.
    "novartis": ["Ciba-Geigy", "Geigy", "Ciba", "CIBA"],
    "novo_company": ["Novo"],
    "orexigen_therapeutics": ["Orexigen Therapeutics"],
    "organon_co": ["Organon"],
    "otsuka_pharmaceutical": ["Otsuka Pharmaceutical"],
    "pfizer": ["Pfizer"],
    "reckitt": ["Reckitt and Colman"],
    "rh_ne_poulenc": ["Rhône-Poulenc", "Rhone-Poulenc", "Rhône-Poulenc S.A."],
    "roche": ["Hoffmann-La Roche", "Roche", "Roche Pharmaceuticals", "Hoffmann-LaRoche"],
    "sandoz": ["Sandoz", "Sandoz Laboratories"],
    # Chinoin redirects to Sanofi too, but it was a Hungarian company, so it is not
    # listed: Sanofi's country is not its (same for Burroughs Wellcome under GSK).
    "sanofi": ["Sanofi-Aventis"],
    "schering_plough": ["Schering Corporation"],
    "sterling_drug": ["Sterling Drug Company"],
    "ucb_company": ["Union Chimique Belge"],
    "wander_ag": ["Wander AG"],
    "warner_lambert": ["Warner-Lambert"],
}

# An infobox row that locates a company (flattened "label | value" table rows).
LOCATION_ROW_RE = re.compile(r"^(?:Headquarters|Country|Country of origin|Founded)\s*\|")
COUNTRY_RE = re.compile("|".join(f"(?:{v['attests']})" for k, v in history.COUNTRIES.items()
                                 if k not in history.SCOPES and v.get("attests")),
                        re.IGNORECASE)

INSTRUCTIONS = (
    "drugs: per drug answer {index, name, company} or null. `index` picks the candidate "
    "that says WHO discovered / first synthesized / developed the drug; `name` is the "
    "company or lab exactly as that sentence writes it (a verbatim substring, e.g. "
    "'Lundbeck', 'Rhône-Poulenc'); `company` is the COMPANY_ARTICLES slug of that "
    "company's own article, or null. A person alone, a university or a government lab "
    "counts only as stated; a later licensee or marketer is not the originator. "
    "companies: per slug answer {country: {index, country} | null, now: {index, name} | "
    "null}: `country` is the vocabulary id of where the company is based, from a "
    "Headquarters row or a sentence naming it; `now` is the company's current name ONLY "
    "when a candidate says it was acquired / merged / renamed into it (`name` verbatim); "
    "a chain over several sentences is {picks: [{index, qid}, ...], name}.") + ECHO_QID


def article_path(slug: str) -> Path:
    return page_path(Path(wikistore.PAGES_DIR), slug)


def _candidate(page: str, line: str) -> dict:
    return {"corpus": CORPUS, "page": page, "line": line}


def drug_candidates(drug: dict) -> list[dict]:
    """The drug's offered sentences: lead + history-like sections, originator words."""
    en = wikistore.page_for(drug)
    if not en or not os.path.exists(en):
        return []
    slug = os.path.splitext(os.path.basename(en))[0]
    text = Path(en).read_text("utf-8", errors="replace")
    out, seen = [], set()
    for s in fetch_drug_history.section_sentences(text, CORPUS):
        if s in seen or len(s) > MAX_LINE or not origin.ORIGINATOR_RE.search(s):
            continue
        seen.add(s)
        out.append(_candidate(slug, s))
    return out


def company_candidates(slug: str) -> list[dict]:
    """A company article's location rows, then its country / successor sentences."""
    path = article_path(slug)
    if not path.exists():
        return []
    text = path.read_text("utf-8", errors="replace")
    rows = [ln.strip() for ln in text.splitlines() if LOCATION_ROW_RE.match(ln.strip())]
    out, seen = [], set()
    for s in rows + fetch_drug_history.section_sentences(text, CORPUS):
        if s in seen or len(s) > MAX_LINE:
            continue
        if not (s in rows or COUNTRY_RE.search(s) or origin.SUCCESSOR_RE.search(s)):
            continue
        seen.add(s)
        out.append(_candidate(slug, s))
    return out


def build(only: set[str] | None = None) -> dict:
    """``{instructions, vocabulary, drugs: {id: {name, candidates}}, companies: {...}}``."""
    drugs: dict[str, dict] = {}
    for drug in drugs_io.load_drugs():
        if only and drug["id"] not in only:
            continue
        cands = drug_candidates(drug)
        if cands:
            drugs[drug["id"]] = {"name": drug.get("name") or drug["id"], "candidates": cands}
    companies = {slug: {"names": names, "candidates": company_candidates(slug)}
                 for slug, names in COMPANY_ARTICLES.items()}
    vocab = {k: v["en"] for k, v in history.COUNTRIES.items() if k not in history.SCOPES}
    return {"instructions": INSTRUCTIONS, "vocabulary": {"countries": vocab},
            "drugs": drugs, "companies": companies}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated drug ids to scope the scan to")
    ap.add_argument("--out", type=Path, default=OUT_PATH, help="worklist output path")
    args = ap.parse_args()
    only = {d.strip() for d in args.only.split(",") if d.strip()} if args.only else None
    wl = build(only)
    if only and args.out.exists():
        wl = merge_scoped(json.loads(args.out.read_text("utf-8")), wl, "drugs")
    worklist_io.write(args.out, wl)
    n = sum(len(v["candidates"]) for v in wl["drugs"].values())
    missing = [s for s, c in wl["companies"].items() if not c["candidates"]]
    print(f"[ok] wrote {args.out}: {len(wl['drugs'])} drugs, {n} candidates, "
          f"{len(wl['companies'])} company articles")
    for slug in missing:
        print(f"  [warn] company article {slug} not stored or offers nothing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
