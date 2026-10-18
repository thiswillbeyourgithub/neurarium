#!/usr/bin/env python
"""Fetch each drug's physicochemical properties (PubChem, corpus ``pubchem``) and its
measured blood-brain-barrier label (B3DB, corpus ``b3db``).

Three drug node kinds come out of this pass (see ``docs/DRUGS.md`` "Physicochemistry and
brain entry"), every one code-read (``extraction: "code"``, no model, no judge):

* ``drug_lipophilicity``: PubChem's computed **XLogP3** (log of the octanol/water
  partition coefficient);
* ``drug_polar_surface``: PubChem's computed **topological polar surface area** (Å²);
* ``drug_bbb``: B3DB's curated **BBB+ / BBB-** label, plus its **logBB** (log10 of the
  brain/blood concentration ratio) where a study measured one.

The join, per roster drug:

1. A **combination** product (a slash-titled article such as ``Naltrexone/bupropion``, or
   a drug carrying ``constituents``) gets nothing: one compound's properties are not the
   combination's.
2. Its **PubChem CID** is the first id on the ``PubChem CID | <n>`` row of its stored
   English Wikipedia drugbox (``lib.corpora.wikipedia.page_for``; the salt ids after it,
   ``2130 as HCl: 64150``, are ignored). No row, no node.
3. PubChem's batch property call gives XLogP3, TPSA, molecular weight, formula and the
   standard InChI, stored as ``data_sources/pubchem/pages/<cid>.md``. A CID whose InChI
   has several components (``2Li.CH2O3``, lithium carbonate; ``C4H8O3.Na``, sodium
   oxybate) is a salt or mixture, whose computed properties are not the active
   molecule's, and an inorganic one (no carbon: Li+, xenon) is outside what the
   lipophilicity and polar-surface rules of thumb describe: nothing is published for
   either.
4. B3DB rows are matched by **CID** (a row's CID cell can list several ids), else, only
   when no row carries the CID, by an **exact case-folded name** (``compound_name`` ==
   the drug's name), the name first passed through ``tools/chirality.py`` so a
   ``(-)-``-tagged row never stands for a racemate. Either way a row is kept only when
   its InChI has the **same formula and connectivity layers** as the drug's PubChem
   InChI (:func:`inchi_core`): B3DB carries name-only rows whose structure is another
   molecule (a "scopolamine" row drawing an amino-cyclopropane, BBB-), and this is what
   refuses them, while a tautomer (olanzapine's CID 135398745, drugbox 4585) passes.
5. Several kept rows that disagree on BBB+/BBB- publish nothing (``conflict``); logBB is
   the range of the values the rows state.

Outputs: author-side (gitignored ``data_sources/``) ``pubchem/pages/<cid>.md``,
``b3db/B3DB_classification.tsv`` (the bulk download) and ``b3db/pages/<page>.md`` (one
flattened row per line, ``page`` = the row's first CID, else its normalized name), and
the committed ``tools/generated_cache/physchem.json`` that ``generate_data.py`` reads
(stdlib, offline).

Run from the repo root::

    python tools/fetch/fetch_physchem.py                  # fetch what is missing
    python tools/fetch/fetch_physchem.py --refresh        # re-download everything
    python tools/fetch/fetch_physchem.py --only citalopram,olanzapine

then ``python tools/fetch/stamp_fetch_dates.py`` and ``python tools/generate_data.py``.
PubChem data is public domain; B3DB is CC0 1.0.

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))
from lib import chirality  # noqa: E402
from lib.io_atomic import atomic_write_json  # noqa: E402
from lib import drugs_io  # noqa: E402
from lib import polite_http  # noqa: E402 (the one polite GET)
from lib.corpora.wikipedia import page_for  # noqa: E402

PUBCHEM_DIR = ROOT / "data_sources" / "pubchem" / "pages"
B3DB_DIR = ROOT / "data_sources" / "b3db"
B3DB_TSV = B3DB_DIR / "B3DB_classification.tsv"
B3DB_PAGES = B3DB_DIR / "pages"
CACHE_PATH = ROOT / "tools" / "generated_cache" / "physchem.json"
B3DB_URL = "https://raw.githubusercontent.com/theochem/B3DB/main/B3DB/B3DB_classification.tsv"
PUBCHEM_PROPS = ("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{ids}/property/"
                 "XLogP,TPSA,MolecularWeight,MolecularFormula,InChI,Title/JSON")
PUBCHEM_PAGE = "https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
BATCH = 100          # CIDs per PubChem property call (well under its URL limit)
PAUSE_S = 0.4        # PubChem asks for at most 5 requests per second

# The page lines, one per property: the quote IS the line (code copied, no judge).
LABELS = {"xlogp": "XLogP3", "tpsa": "Topological polar surface area",
          "mw": "Molecular weight", "formula": "Molecular formula"}
UNITS = {"tpsa": " Å²", "mw": " g/mol"}

_CID_ROW = re.compile(r"^PubChem CID \| *(\d+)", re.M)


# ---------------------------------------------------------------------------
# The join (pure functions, unit tested in tools/tests/test_physchem.py)
# ---------------------------------------------------------------------------

def is_combination(drug: dict) -> bool:
    """No single molecule to read: a combination (``drugs_io.is_combination``) or a salt
    declaring its ``constituents``."""
    return drugs_io.is_combination(drug) or bool(drug.get("constituents"))


def drugbox_cid(text: str) -> int | None:
    """The first id on a stored article's ``PubChem CID | ...`` row, or None."""
    m = _CID_ROW.search(text or "")
    return int(m.group(1)) if m else None


def row_cids(cell: str) -> list[int]:
    """The ids of a B3DB CID cell (``"3889.0|"``, ``"5184"``, ``"1|2"``), in order."""
    out = []
    for part in (cell or "").split("|"):
        part = part.strip()
        if part:
            try:
                out.append(int(float(part)))
            except ValueError:
                continue
    return out


def inchi_core(inchi: str) -> str | None:
    """The formula + connectivity layers of a standard InChI (``C17H20N4S/c1-12-...``),
    the part a tautomer or a stereo variant shares and another molecule does not."""
    if not inchi or not inchi.startswith("InChI="):
        return None
    layers = inchi.split("/")
    formula = layers[1] if len(layers) > 1 else ""
    conn = next((x for x in layers[2:] if x.startswith("c")), "")
    return f"{formula}/{conn}"


def compound_skip(inchi: str | None) -> str | None:
    """Why a drugbox compound gets no node, or None: a salt or mixture (several InChI
    components, ``C4H8O3.Na``) or an inorganic one (no carbon in its Hill formula)."""
    core = inchi_core(inchi or "")
    if not core:
        return "no InChI"
    formula = core.split("/")[0]
    if "." in formula:
        return "a salt or mixture"
    if not re.match(r"\d*C(?![a-z])", formula):
        return "inorganic"
    return None


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().casefold())


def name_matches(row_name: str, drug: dict) -> bool:
    """An EXACT case-folded name match, stereo-guarded by tools/chirality.py."""
    stem, tag = chirality.split_stereo(row_name or "")
    return (_norm(stem) == _norm(drug["name"])
            and chirality.tag_allowed(tag, drug["id"]))


def match_rows(drug: dict, cid: int, inchi: str | None, rows: list[dict]):
    """``(how, kept, refused)``: the B3DB rows standing for ``drug``.

    ``how`` is ``"cid"`` or ``"name"`` (the rule that found candidates) or None; ``kept``
    the candidates whose InChI core equals the drug's; ``refused`` the others.
    """
    how = "cid"
    cands = [r for r in rows if cid in row_cids(r.get("CID"))]
    if not cands:
        how = "name"
        cands = [r for r in rows if name_matches(r.get("compound_name"), drug)]
    if not cands:
        return None, [], []
    core = inchi_core(inchi or "")
    kept = [r for r in cands if core and inchi_core(r.get("Inchi") or "") == core]
    return how, kept, [r for r in cands if r not in kept]


def b3db_page_key(row: dict) -> str:
    """The stable page a row lives on: its first CID, else its normalized name."""
    ids = row_cids(row.get("CID"))
    if ids:
        return str(ids[0])
    return re.sub(r"[^a-z0-9]+", "_", _norm(row.get("compound_name"))).strip("_") or "unnamed"


def _num(s: str) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def row_line(row: dict) -> str:
    """One flattened B3DB row, the quote: ``B3DB row 923: olanzapine | CID 135398745 |
    logBB 0.8 | BBB+ | group A | references R18, R26``."""
    refs = ", ".join(x for x in (row.get("reference") or "").split("|") if x)
    cells = [f"B3DB row {row['NO.']}: {row.get('compound_name') or '(unnamed)'}",
             f"CID {row.get('CID') or '-'}",
             f"logBB {row['logBB']}" if row.get("logBB") else "logBB -",
             row["BBB+/BBB-"],
             f"group {row.get('group') or '-'}",
             f"references {refs or '-'}"]
    return " | ".join(cells)


def bbb_claim(kept: list[dict], page: str):
    """``(claim, status)`` from the kept rows, all stored on B3DB page ``page``:
    ``{"label", "logbb"?, "logbb_max"?, "sources"}``, or None with ``"conflict"``."""
    labels = {r["BBB+/BBB-"] for r in kept}
    if len(labels) != 1:
        return None, "conflict"
    claim = {"label": labels.pop()}
    vals = sorted({v for r in kept if (v := _num(r.get("logBB"))) is not None})
    if vals:
        claim["logbb"] = vals[0]
        if vals[-1] != vals[0]:
            claim["logbb_max"] = vals[-1]
    claim["sources"] = [{"corpus": "b3db", "page": page, "quote": row_line(r),
                         "provenance": "verified", "extraction": "code"}
                        for r in sorted(kept, key=lambda r: int(r["NO."]))]
    return claim, "found"


def pubchem_page(cid: int, props: dict, fetched: str) -> str:
    """The quote-gate page of one compound: a provenance header, then one line per
    property (the quote is the line)."""
    out = [f"# PubChem compound {cid}: {props.get('Title') or '(untitled)'}",
           f"cid: {cid}",
           f"source: {PUBCHEM_PAGE.format(cid=cid)}",
           f"fetched: {fetched}",
           "computed by PubChem (XLogP3 3.0; Cactvs TPSA); public domain", ""]
    for key, prop in (("xlogp", "XLogP"), ("tpsa", "TPSA"), ("mw", "MolecularWeight"),
                      ("formula", "MolecularFormula")):
        if props.get(prop) not in (None, ""):
            out.append(f"{LABELS[key]}: {props[prop]}{UNITS.get(key, '')}")
    if props.get("InChI"):
        out.append(f"InChI: {props['InChI']}")
    return "\n".join(out) + "\n"


def parse_page(text: str) -> dict:
    """Read a stored PubChem page back: ``{"xlogp", "tpsa", "inchi"}`` (floats/str)."""
    out = {}
    for key in ("xlogp", "tpsa"):
        m = re.search(rf"^{re.escape(LABELS[key])}: (-?[\d.]+)", text, re.M)
        if m:
            out[key] = float(m.group(1))
    m = re.search(r"^InChI: (\S+)", text, re.M)
    if m:
        out["inchi"] = m.group(1)
    return out


def pubchem_claims(cid: int, text: str) -> dict:
    """The ``xlogp`` / ``tpsa`` cache entries of one stored page, each with its quote."""
    vals = parse_page(text)
    out = {}
    for key in ("xlogp", "tpsa"):
        if key in vals:
            line = next(ln for ln in text.splitlines() if ln.startswith(LABELS[key] + ": "))
            out[key] = {"value": vals[key],
                        "sources": [{"corpus": "pubchem", "page": str(cid), "quote": line,
                                     "provenance": "verified", "extraction": "code"}]}
    return out


# ---------------------------------------------------------------------------
# Network + files
# ---------------------------------------------------------------------------

def fetch_pubchem(cids: list[int], refresh: bool) -> None:
    """Write ``pubchem/pages/<cid>.md`` for every CID lacking one (all with --refresh)."""
    PUBCHEM_DIR.mkdir(parents=True, exist_ok=True)
    todo = [c for c in cids if refresh or not (PUBCHEM_DIR / f"{c}.md").exists()]
    today = _dt.date.today().isoformat()
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        url = PUBCHEM_PROPS.format(ids=",".join(map(str, chunk)))
        data = json.loads(polite_http.fetch(url))
        for props in data["PropertyTable"]["Properties"]:
            (PUBCHEM_DIR / f"{props['CID']}.md").write_text(
                pubchem_page(props["CID"], props, today), encoding="utf-8")
        time.sleep(PAUSE_S)
    print(f"PubChem: {len(todo)} compound(s) fetched, {len(cids) - len(todo)} stored")


def load_b3db(refresh: bool) -> list[dict]:
    """The B3DB classification rows (downloading the TSV once, or with --refresh)."""
    if refresh or not B3DB_TSV.exists():
        B3DB_DIR.mkdir(parents=True, exist_ok=True)
        B3DB_TSV.write_bytes(polite_http.fetch(B3DB_URL))
        print(f"B3DB: downloaded {B3DB_URL}")
    with B3DB_TSV.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_b3db_pages(cited: dict[str, list[dict]], fetched: str) -> None:
    """One page per cited key: the header, then each row's quote line + its InChI."""
    B3DB_PAGES.mkdir(parents=True, exist_ok=True)
    for page, rows in cited.items():
        out = [f"# B3DB classification rows: {page}", f"source: {B3DB_URL}",
               f"fetched: {fetched}", "licence: CC0 1.0", ""]
        for r in sorted({r["NO."]: r for r in rows}.values(), key=lambda r: int(r["NO."])):
            out += [row_line(r), f"B3DB row {r['NO.']} InChI: {r.get('Inchi') or '-'}"]
        (B3DB_PAGES / f"{page}.md").write_text("\n".join(out) + "\n", encoding="utf-8")


def build(drugs: list[dict], rows: list[dict], fetched: str):
    """``(entries, skipped, cited)``: cache entry per drug id, why each other drug got
    nothing, and the B3DB rows each page must hold."""
    entries, skipped, cited = {}, {}, {}
    for drug in drugs:
        did = drug["id"]
        if is_combination(drug):
            skipped[did] = "combination"
            continue
        path = page_for(drug)
        cid = drugbox_cid(Path(path).read_text(encoding="utf-8")) if path else None
        if cid is None:
            skipped[did] = "no PubChem CID in the drugbox"
            continue
        page = PUBCHEM_DIR / f"{cid}.md"
        if not page.exists():
            skipped[did] = f"PubChem page {cid} not fetched"
            continue
        text = page.read_text(encoding="utf-8")
        inchi = parse_page(text).get("inchi")
        why = compound_skip(inchi)
        if why:
            skipped[did] = f"PubChem CID {cid}: {why}"
            continue
        entry = {"cid": cid, **pubchem_claims(cid, text)}
        how, kept, refused = match_rows(drug, cid, inchi, rows)
        if refused:
            entry["b3db_refused"] = [int(r["NO."]) for r in refused]
        if kept:
            key = str(cid) if how == "cid" else b3db_page_key(kept[0])
            claim, status = bbb_claim(kept, key)
            if claim:
                claim["match"] = how
                entry["bbb"] = claim
                cited.setdefault(key, []).extend(kept)
            else:
                entry["b3db_conflict"] = sorted(
                    f"row {r['NO.']}: {r['BBB+/BBB-']}" for r in kept)
        entries[did] = entry
    return entries, skipped, cited


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true",
                    help="re-download every PubChem page and the B3DB TSV")
    ap.add_argument("--only", help="comma-separated drug ids (others keep their entry)")
    args = ap.parse_args()
    drugs = drugs_io.load_drugs()
    if args.only:
        want = set(args.only.split(","))
        drugs = [d for d in drugs if d["id"] in want]
    cids = sorted({c for d in drugs if not is_combination(d)
                   for p in [page_for(d)] if p
                   for c in [drugbox_cid(Path(p).read_text(encoding="utf-8"))] if c})
    fetch_pubchem(cids, args.refresh)
    rows = load_b3db(args.refresh)
    fetched = _dt.date.fromtimestamp(B3DB_TSV.stat().st_mtime).isoformat()
    entries, skipped, cited = build(drugs, rows, fetched)
    write_b3db_pages(cited, fetched)
    if not args.only:   # a page no drug cites any more is dropped (scoped runs keep all)
        for stale in B3DB_PAGES.glob("*.md"):
            if stale.stem not in cited:
                stale.unlink()
    prior = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if (
        args.only and CACHE_PATH.exists()) else {"drugs": {}, "skipped": {}}
    for did in {d["id"] for d in drugs}:
        prior["drugs"].pop(did, None)
        prior["skipped"].pop(did, None)
    prior["drugs"].update(entries)
    prior["skipped"].update(skipped)
    atomic_write_json(CACHE_PATH, prior, indent=1, sort_keys=True)
    vals = prior["drugs"].values()
    print(f"{len(rows)} B3DB rows; {sum('xlogp' in e for e in vals)} XLogP3, "
          f"{sum('tpsa' in e for e in vals)} TPSA, {sum('bbb' in e for e in vals)} BBB "
          f"({sum(e.get('bbb', {}).get('match') == 'name' for e in vals)} by name), "
          f"{sum('b3db_conflict' in e for e in vals)} conflict(s), "
          f"{len(prior['skipped'])} drug(s) skipped -> {CACHE_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
