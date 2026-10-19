#!/usr/bin/env python
"""Store each drug's French summary of product characteristics as corpus #16 (BDPM).

The French public drug database (ANSM "Base de données publique des médicaments", BDPM,
Licence Ouverte / Etalab) is the French counterpart of DailyMed (corpus #14): every
medicine authorised in France, with its official summary of product characteristics
(RCP). Its section 5.2 "Propriétés pharmacocinétiques" states a time to peak and an
elimination half-life for most drugs, including the European-only ones DailyMed cannot
reach (no US label exists for loprazolam, cyamemazine, tiapride...). Its product table
also names every French commercial brand, which is the third fact read here.

This is a **corpus fetcher**, not a claim pass: it states nothing, it only puts pages on
disk in the shape every other corpus uses, so ``fetch_tmax.py`` / ``fetch_half_life.py``
can offer sentences and ``apply_tmax.py`` / ``apply_half_life.py`` /
``apply_brand_names.py --bdpm`` can gate quotes against them.

What it stores:

* ``data_sources/bdpm/CIS_bdpm.txt`` + ``CIS_COMPO_bdpm.txt`` - the two bulk tables
  (latin-1 TSV): one row per product (CIS code, denomination, form, route, status,
  commercialisation) and one row per active-substance line of a product.
* ``data_sources/bdpm/raw/<CIS>.html`` - the product's RCP page as downloaded.
* ``data_sources/bdpm/pages/<CIS>.md`` - the quote-gate page: a header (denomination,
  CIS, form, route, holder, source URL, fetch date) then the RCP section 5.2 paragraphs,
  one per line. A product cited only for its brand name gets the header alone, written
  from the bulk table (its denomination is the brand quote), with no RCP download.
* ``tools/generated_cache/bdpm_labels.json`` - per drug: the chosen RCP (``cis``,
  denomination, ``why``) and the French brands read off the product table.

The join, drug -> French INN -> products, is the part that can silently go wrong:

* a product counts only when it has exactly ONE active substance (a combination's RCP
  states the combination's kinetics, the same rule as DailyMed);
* a substance line is reduced to its molecule (``CHLORHYDRATE DE FLUOXÉTINE``,
  ``CITALOPRAM (BROMHYDRATE DE)``, ``FLUOXÉTINE BASE`` -> ``FLUOXETINE``) and compared
  **exactly**, accent-folded, against the drug's names (English name, the French
  Wikipedia title the brand pass resolved, ``FR_ALIASES``). Exact, never a prefix or
  substring, so ``ESCITALOPRAM`` can never match citalopram; a stereo-tagged substance
  goes through ``tools/chirality.py`` like every other name-joined corpus;
* homeopathic dilutions ("... POUR PRÉPARATIONS HOMÉOPATHIQUES") are not the drug.

The representative RCP: commercialised, active authorisation, plain oral (not
"LP" / "à libération prolongée" / modified-release / gastro-resistant: a prolonged-release
product states a real Tmax of a different product, the Seroquel XR gotcha), brand-name
product before a generic; up to ``MAX_TRIES`` are downloaded until one's 5.2 states a
peak or a half-life. Only when no plain-oral product exists is a non-modified-release
product of another route tried, and ``why`` says so.

Brands: the denomination's brand part, see :func:`brand_of` (the generic-exclusion rule
lives there).

Usage (from the repo root)::

    python tools/fetch/fetch_bdpm.py                 # drugs lacking a tmax or a half-life
    python tools/fetch/fetch_bdpm.py --all           # every roster drug
    python tools/fetch/fetch_bdpm.py --only loprazolam,tiapride
    python tools/fetch/fetch_bdpm.py --refresh       # re-download tables + RCPs

Network, polite (one request at a time, ``polite_http.PAUSE_S`` apart) and resumable.
Stdlib only; author-side (``data_sources/`` is gitignored).

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent           # repo root
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE))

from lib.page_file import page_path  # noqa: E402 (refuses a path-like page)
from lib.corpora import bdpm                                    # noqa: E402 (the store + product join)
from lib import drugs_io                                                 # noqa: E402
from lib.io_atomic import atomic_write_json                         # noqa: E402
from lib import polite_http                                              # noqa: E402 (the one polite GET)
import fetch_half_life                                          # noqa: E402 (HALF_LIFE_RE)
from lib.parse import durations  # noqa: E402

MAX_TRIES = 4        # RCPs downloaded per drug before giving up on it


# ---------------------------------------------------------------------------- RCP


def section_52(page_html: str) -> list[str]:
    """The RCP section 5.2 as text lines, one paragraph per line ([] when absent)."""
    body = bdpm.section_body(page_html, "5.2", "RcpPropPharmacocinetiques")
    return bdpm.html_lines(body) if body is not None else []


def states_pk(lines: list[str]) -> bool:
    """Whether any line names a peak or a half-life AND carries a duration."""
    return any((durations.PEAK_RE.search(ln) or fetch_half_life.HALF_LIFE_RE.search(ln))
               and durations.durations_in_fr(ln) for ln in lines)


def page_text(product: dict, lines: list[str]) -> str:
    """The stored page: provenance header, then the 5.2 lines (none for a brand page)."""
    head = [f"# {product['denomination']}", f"cis: {product['cis']}",
            f"form: {product['form']}", f"route: {product['route']}",
            f"holder: {product['holder']}", f"source: {bdpm.RCP_URL.format(cis=product['cis'])}",
            f"fetched: {time.strftime('%Y-%m-%d')}", ""]
    return "\n".join(head + lines) + "\n"


def write_page(product: dict, lines: list[str]) -> None:
    bdpm.PAGES_DIR.mkdir(parents=True, exist_ok=True)
    page_path(bdpm.PAGES_DIR, product['cis']).write_text(page_text(product, lines),
                                                    encoding="utf-8")


def fetch_rcp(drug: dict, ranked: list[tuple[dict, str]], *, refresh: bool,
              entry: dict) -> str:
    """Store one drug's representative RCP into ``entry``; returns a one-word outcome."""
    if not ranked:
        return "no-ir-product"            # only modified-release forms are marketed
    tried = 0
    for product, why in ranked:
        raw_path = bdpm.RAW_DIR / f"{product['cis']}.html"
        if refresh or not raw_path.exists():
            if tried >= MAX_TRIES:
                break
            body = polite_http.fetch_or_none(bdpm.RCP_URL.format(cis=product["cis"]))
            tried += 1
            if not body:
                continue
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(body, encoding="utf-8")
        else:
            body = raw_path.read_text(encoding="utf-8", errors="replace")
        lines = section_52(body)
        if not lines or not states_pk(lines):
            continue
        write_page(product, lines)
        entry["cis"] = product["cis"]
        entry["denomination"] = product["denomination"]
        entry["why"] = why
        return "stored"
    return "no-pk"


def download_tables(refresh: bool) -> None:
    for name in (bdpm.PRODUCTS_FILE, bdpm.COMPO_FILE):
        path = bdpm.BASE_DIR / name
        if refresh or not path.exists():
            body = polite_http.fetch_or_none(bdpm.TABLE_URL.format(name=name), binary=True)
            if body is None:
                raise SystemExit(f"[error] could not download {name}")
            bdpm.BASE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated drug ids to scope the run to")
    ap.add_argument("--all", action="store_true",
                    help="fetch an RCP for every roster drug, not only those lacking "
                         "a tmax or a half-life")
    ap.add_argument("--refresh", action="store_true",
                    help="re-download the tables and every RCP")
    args = ap.parse_args()
    only = {d.strip() for d in args.only.split(",") if d.strip()} if args.only else None

    download_tables(args.refresh)
    products = bdpm.load_products(bdpm.read_table(bdpm.BASE_DIR / bdpm.PRODUCTS_FILE))
    compo = bdpm.load_compo(bdpm.read_table(bdpm.BASE_DIR / bdpm.COMPO_FILE))
    titles = bdpm.fr_titles()
    cache = (json.loads(bdpm.CACHE_PATH.read_text(encoding="utf-8"))
             if bdpm.CACHE_PATH.exists() else {})

    counts: dict[str, int] = {}
    drugs = [d for d in drugs_io.load_drugs() if not only or d["id"] in only]
    for i, drug in enumerate(drugs, 1):
        did = drug["id"]
        if drugs_io.is_combination(drug):
            outcome = "combo"                # a combination's RCP is not this drug's
            cache.pop(did, None)
        else:
            keys = bdpm.drug_keys(drug, titles)
            found = bdpm.products_for(drug, keys, products, compo)
            entry = cache.get(did, {}) if not args.refresh else {}
            entry["brands"] = bdpm.brands_for(found, keys)
            for b in entry["brands"]:
                if not page_path(bdpm.PAGES_DIR, b['cis']).exists():
                    write_page(products[b["cis"]], [])
            wants = args.all or only or not drug.get("tmax") or not drug.get("half_life")
            cached = entry.get("cis") and page_path(bdpm.PAGES_DIR, entry['cis']).exists()
            if not found:
                outcome = "no-product"
            elif cached and not args.refresh:
                outcome = "cached"
            elif wants:
                outcome = fetch_rcp(drug, bdpm.rank(found, keys), refresh=args.refresh,
                                    entry=entry)
            else:
                outcome = "brands-only"
            if found:
                cache[did] = entry
            else:
                cache.pop(did, None)
        counts[outcome] = counts.get(outcome, 0) + 1
        print(f"[{i}/{len(drugs)}] {did}: {outcome}")
        if outcome == "stored":
            atomic_write_json(bdpm.CACHE_PATH, cache, indent=1, sort_keys=True)
    bdpm.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(bdpm.CACHE_PATH, cache, indent=1, sort_keys=True)
    print("[ok] " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
          + f" -> {bdpm.CACHE_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
