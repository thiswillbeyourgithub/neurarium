#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pymupdf>=1.24",
# ]
# ///
"""Read the AGNP TDM consensus guideline's two drug tables (corpus #19 ``agnp_tdm``).

The guideline (Hart XM et al., "Consensus Guidelines for Therapeutic Drug Monitoring
in Neuropsychopharmacology: Update 2026", Pharmacopsychiatry 2026;59:166-295) is a
book-like PDF corpus: split to ``data_sources/books/agnp_tdm_2026/pages/<n>.md`` by
``tools/fetch/pdf_to_pages.py`` (author-side, gitignored). Two of its tables carry
per-drug facts this pass reads with pymupdf's table finder, pure code, no model:

- **Table 5** (PDF pages 20-52, landscape): the therapeutic reference range, the
  laboratory alert level and the level of recommendation to use TDM. A drug's
  **first** row only, and only when each cell is one unambiguous value
  (:func:`parse_range`): a cell holding two ranges (desipramine's depression vs
  chronic-pain ranges), a range qualified by population or dose ("for children 6-12
  y", "after 200 mg/d") or "Not established" writes nothing and is listed under
  ``skipped`` instead, since picking one of two would be a judgement the table does
  not make.
- **Table 1** (PDF pages 7-11): the enzymes and transporters metabolising each drug.
  A quote is offered per (drug, enzyme) the table names, and the generator
  (``data_generators/tdm.merge_enzymes``) attaches it to the substrate row another
  corpus states, or adds the row when none does.

The quote is the table row's cells copied by code in the page's own reading order
(``extraction: "code"``, so no judge), and is written only once it is found on the
stored page by ``lib.quote_match.normalize_for_match``, the gate ``check_data.py`` runs.

Writes ``tools/generated_cache/agnp_tdm.json`` (committed: the parsed values plus one
row quote per drug, never the table) and the generated drug -> pages table at the end of
``data_sources/books/agnp_tdm_2026/INDEX.md`` (author-side).

Usage (from the repo root)::

    uv run tools/fetch/fetch_agnp_tdm.py

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from lib import drugs_io  # noqa: E402
from lib.io_atomic import atomic_write_json  # noqa: E402
from lib.quote_match import normalize_for_match  # noqa: E402  (the gate's own normalizer)
from lib.text_fold import alnum_key  # noqa: E402
from pipeline.gate import PageGate  # noqa: E402 (the one quote gate)

CORPUS = "agnp_tdm"
BOOK = ROOT / "data_sources" / "books" / "agnp_tdm_2026"
PDF = BOOK / "a-2860-7861.pdf"
PAGES_DIR = BOOK / "pages"
INDEX = BOOK / "INDEX.md"
CACHE_PATH = ROOT / "tools" / "generated_cache" / "agnp_tdm.json"

TABLE1_PAGES = range(7, 12)    # 1-based PDF pages
TABLE5_PAGES = range(20, 53)

# Table 5 is printed sideways, so the table finder returns it transposed: one grid row
# per table column, read bottom-up. These are its columns in that grid order (page 20,
# the first, has no header column and no blank title row).
TABLE5_FIELDS = ("refs", "title", "comments", "cf", "level", "alert", "tss",
                 "indication", "trr", "time", "drug")
# The cells a row quote is built from, in the order the page's text layer reads them.
QUOTE_FIELDS = ("drug", "time", "trr", "indication", "tss", "alert", "level")

# Table-row drug names that are not one of our ids or names once folded. A table row
# naming two substances (ketamine/esketamine) is one range the table gives for both.
ALIASES = {
    "valproicacid": ["valproate"],
    "morphinesulfate": ["morphine"],
    "diacetylmorphineheroin": ["heroin"],
    "dothiepindosulepin": ["dothiepin"],
    "ketamineesketamine": ["ketamine", "esketamine"],
    "paliperidonehydroxyrisperidone": ["paliperidone"],
    "flupentixol": ["flupenthixol"],
    "chloralhydrate": ["chloral_hydrate"],
    "δ9transtetrahydrocannabinolthcmedicalcannabis": ["thc"],
    "xanomelineandtrospiumchloride": ["xanomeline"],
    "clobazamnorclobazam": ["clobazam"],
    "amfetaminedexamfetamineandlisdexamfetamine": ["amphetamine_dl"],
    "dextroamfetamine": ["amphetamine_d"],
    "methylphenidate": ["methylphenidate_dl"],      # the racemate, as printed
    "lisdexamphetamineldx": ["lisdexamfetamine"],
    "gammahydroxybutyricacidghb": ["sodium_oxybate"],
    # Table 1's own spellings.
    "cocain": ["cocaine"], "eszopiclon": ["eszopiclone"], "zaleplone": ["zaleplon"],
    "safinamid": ["safinamide"],
}

# Analyte abbreviations the table's own legend (page 52) spells out.
ANALYTE_ABBREVIATIONS = {"NF": "N-desalkylflurazepam", "MHD": "10-hydroxycarbazepine"}

_NUM = r"\d[\d,]*(?:\.\d+)?"
_UNIT = r"(?:ng|µg|μg|pg)\s*/\s*m[lL]|mmol\s*/\s*L"
RANGE_RE = re.compile(rf"^(?P<lo>{_NUM})\s*[–-]\s*(?P<hi>{_NUM})\s*(?P<unit>{_UNIT})"
                      r"\s*(?:\((?P<analyte>[^()]+)\))?$")
VALUE_RE = re.compile(rf"^(?P<v>{_NUM})\s*(?P<unit>{_UNIT})"
                      r"\s*(?:\((?P<analyte>[^()]+)\))?$")
LEVEL_RE = re.compile(r"^\+?\s*(?P<level>[1-4])$")
ENZYME_RE = re.compile(r"^(CYP\d[A-Z]\d+|UGT\d[A-Z]\d+|UGT|FMO3)$")


def clean(cell: str | None) -> str:
    """One table cell as running text, folded the way the quote gate folds a page.

    A line break after a hyphen or soft hyphen joins the word (so "Ampheta-/mine"
    reads "Amphetamine", exactly as ``normalize_for_match`` reads the page); every
    other break is a space; the table's "+" (revised since 2018) marker and zero-width
    spaces are dropped.

    >>> clean("Brexpi\\u00ad\\n+\\nprazole")
    'Brexpiprazole'
    >>> clean("200–550 ng/\\nmL")
    '200–550 ng/ mL'
    """
    t = (cell or "").replace("​", "")
    t = re.sub(r"(?m)^\s*\+\s*$\n?", "", t)       # a "+" alone on its line
    t = re.sub(r"\s\+(?=\s|$)", " ", t)              # or trailing a name
    t = re.sub(r"^\+\s+", "", t)
    t = re.sub("­\\s*", "", t)
    t = re.sub(r"-\s*\n\s*", "", t)
    return " ".join(t.split())


def _num(s: str) -> float:
    v = float(s.replace(",", ""))
    return int(v) if v.is_integer() else v


def _unit(s: str) -> str:
    s = re.sub(r"\s+", "", s).replace("μ", "µ")
    return s[:-2] + "mL" if s.lower().endswith("/ml") else s


def _analyte(s: str | None) -> str | None:
    """A parenthesised analyte, language-neutral: "plus" becomes "+"."""
    if not s:
        return None
    s = " ".join(s.split())
    s = ANALYTE_ABBREVIATIONS.get(s, s)
    return re.sub(r"\s+plus\s+", " + ", s)


def parse_range(cell: str) -> dict | None:
    """``{low, high, unit, analyte?}`` for a cell holding exactly one range, else None.

    >>> parse_range("850–1,500 ng/mL (hydroxybu- propion)".replace("- ", ""))
    {'low': 850, 'high': 1500, 'unit': 'ng/mL', 'analyte': 'hydroxybupropion'}
    >>> parse_range("60–350 ng/mL 10–60 ng/mL") is None
    True
    """
    m = RANGE_RE.match(cell)
    if not m:
        return None
    out = {"low": _num(m["lo"]), "high": _num(m["hi"]), "unit": _unit(m["unit"])}
    if out["low"] >= out["high"]:
        return None
    if _analyte(m["analyte"]):
        out["analyte"] = _analyte(m["analyte"])
    return out


def parse_value(cell: str) -> dict | None:
    """``{value, unit, analyte?}`` for a cell holding exactly one level, else None."""
    m = VALUE_RE.match(cell)
    if not m:
        return None
    out = {"value": _num(m["v"]), "unit": _unit(m["unit"])}
    if _analyte(m["analyte"]):
        out["analyte"] = _analyte(m["analyte"])
    return out


def parse_level(cell: str) -> int | None:
    m = LEVEL_RE.match(cell)
    return int(m["level"]) if m else None


def table5_rows(grids: list[dict]) -> list[dict]:
    """Every Table 5 row as ``{page, <field>: cleaned cell}``, continuation rows kept
    (their ``drug`` is empty) so a caller can tell a drug's first row from the rest."""
    rows = []
    for g in grids:
        grid = g["grid"]
        fields = TABLE5_FIELDS if len(grid) == len(TABLE5_FIELDS) else \
            tuple(f for f in TABLE5_FIELDS if f != "title")
        if len(grid) != len(fields):
            raise ValueError(f"page {g['page']}: Table 5 grid has {len(grid)} rows")
        for j in range(len(grid[0])):
            rec = {f: clean(grid[i][j]) for i, f in enumerate(fields)}
            if rec["drug"].startswith("Drugs and active") or not any(
                    rec[f] for f in QUOTE_FIELDS):
                continue            # the header column, or an empty trailing one
            rec["page"] = g["page"]
            rows.append(rec)
    return rows


def roster_index(drugs: list[dict]) -> dict[str, list[str]]:
    """Folded name -> drug ids: each id and English name, then :data:`ALIASES`."""
    idx: dict[str, list[str]] = {}
    for d in drugs:
        name = d["name"] if isinstance(d["name"], str) else d["name"].get("en", "")
        for key in {alnum_key(d["id"]), alnum_key(name)}:
            idx.setdefault(key, [])
            if d["id"] not in idx[key]:
                idx[key].append(d["id"])
    for key, ids in ALIASES.items():
        idx[key] = list(ids)
    return idx


def drug_ids(name: str, index: dict[str, list[str]]) -> list[str]:
    """Our ids for a table-row drug name: the whole name, else the name before a
    parenthesis ("Clobazam (norclobazam)"), never a word inside it."""
    for key in (alnum_key(name), alnum_key(name.split("(")[0])):
        if key in index:
            return index[key]
    return []


def _source(page: int, quote: str) -> dict:
    return {"corpus": CORPUS, "page": page, "quote": quote,
            "provenance": "verified", "extraction": "code"}


def therapeutic_ranges(rows: list[dict], index: dict[str, list[str]],
                       pages: PageGate) -> tuple[dict, list[dict]]:
    """Per roster drug its first Table 5 row's range, alert level and TDM level.

    Returns ``(ranges, skipped)``; ``skipped`` names every roster drug the table has a
    row for but this pass could not read as one value, and why.
    """
    ranges: dict[str, dict] = {}
    skipped: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if not row["drug"]:
            continue                                    # a continuation row
        ids = [i for i in drug_ids(row["drug"], index) if i not in seen]
        if not ids:
            continue
        seen.update(ids)
        rng = parse_range(row["trr"])
        if not rng:
            skipped += [{"drug": i, "page": row["page"], "why": "range",
                         "cell": row["trr"]} for i in ids]
            continue
        quote = " ".join(row[f] for f in QUOTE_FIELDS if row[f])
        if not pages.on_page(CORPUS, row["page"], quote):
            skipped += [{"drug": i, "page": row["page"], "why": "quote not on page",
                         "cell": quote} for i in ids]
            continue
        rec = dict(rng)
        alert = parse_value(row["alert"])
        if alert:
            rec["alert"] = alert
        level = parse_level(row["level"])
        if level:
            rec["tdm_level"] = level
        rec["sources"] = [_source(row["page"], quote)]
        for i in ids:
            ranges[i] = rec
    return ranges, skipped


# Table 1's caption, header and the legend rows the table finder reads as rows.
SKIP_ROWS = ("Table 1", "Drugs", "Abbreviations", "Note:", "CPIC levels")


def table1_rows(grids: list[dict]) -> list[dict]:
    """Table 1 rows ``{page, drug, enzymes}``; a row the page break split is joined
    back onto its drug (the continuation's drug cell is empty)."""
    rows: list[dict] = []
    for g in grids:
        for r in g["grid"]:
            if len(r) < 2:
                continue
            drug, enz = clean(r[0]), clean(r[1])
            if drug.startswith(SKIP_ROWS) or not (drug or enz):
                continue
            if not drug and rows:
                rows[-1]["more"] = enz              # quoted only from its own page
                continue
            rows.append({"page": g["page"], "drug": drug, "enzymes": enz})
    return rows


def enzyme_tokens(cell: str) -> list[tuple[str, str]]:
    """``(token as printed, our ENZYMES id)`` for each isoform the cell names."""
    out = []
    for tok in re.split(r",\s*", cell):
        tok = tok.strip()
        if ENZYME_RE.match(tok):
            out.append((tok, tok.lower()))
    return out


def enzyme_confirmations(rows: list[dict], index: dict[str, list[str]],
                         pages: PageGate) -> dict[str, list[dict]]:
    """Per roster drug, a substrate row per isoform Table 1 names, each with the
    longest leading run of the row's cell that is on its page and reaches it."""
    out: dict[str, list[dict]] = {}
    for row in rows:
        ids = drug_ids(row["drug"], index)
        if not ids:
            continue
        items = [s.strip() for s in row["enzymes"].split(",")]
        # Longest prefix of the cell found on the page (a wrapped row may interleave
        # with the next column in the page's reading order).
        quoted = 0
        for n in range(len(items), 0, -1):
            if pages.on_page(CORPUS, row["page"], f"{row['drug']} {', '.join(items[:n])}"):
                quoted = n
                break
        for k in range(quoted):
            tok = items[k]
            if not ENZYME_RE.match(tok):
                continue
            quote = f"{row['drug']} {', '.join(items[:quoted])}"
            for i in ids:
                rows_i = out.setdefault(i, [])
                if all(r["enzyme"] != tok.lower() for r in rows_i):
                    rows_i.append({"enzyme": tok.lower(), "role": "substrate",
                                   "sources": [_source(row["page"], quote)]})
    return out


def table1_named(rows: list[dict], index: dict[str, list[str]]) -> dict[str, list[str]]:
    """Every isoform Table 1 names per roster drug, quoted or not (the cross-check)."""
    out: dict[str, list[str]] = {}
    for row in rows:
        cell = row["enzymes"] + (", " + row["more"] if row.get("more") else "")
        for i in drug_ids(row["drug"], index):
            out.setdefault(i, [])
            out[i] += [e for _, e in enzyme_tokens(cell) if e not in out[i]]
    return out


def cell_texts(page, rects: list) -> list[str]:
    """The text inside each table cell (``None`` rect -> ""), line by line.

    Read from the page's own character layer rather than a clipped ``get_text`` per
    cell: a ligature ("fl", "fi") is two characters whose second has a zero-size box
    printed somewhere else, so a clip drops it from its word ("fuoxetine") and may
    leak it into a neighbour cell (fluoxetine's time read "24 hl"), and the row then
    is not on the stored page. Here a zero-size character goes wherever the
    character before it went.
    """
    found: list[list[str]] = [[] for _ in rects]
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            prev = None
            per_cell: dict[int, list[str]] = {}
            for span in line["spans"]:
                for ch in span["chars"]:
                    x0, y0, x1, y1 = ch["bbox"]
                    box = ch["bbox"] if (x1 > x0 and y1 > y0) else prev
                    prev = box
                    if box is None:
                        continue
                    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                    for i, r in enumerate(rects):
                        if r and r[0] <= cx <= r[2] and r[1] <= cy <= r[3]:
                            per_cell.setdefault(i, []).append(ch["c"])
                            break
            for i, chars in per_cell.items():
                found[i].append("".join(chars))
    return ["\n".join(lines) for lines in found]


def read_grids(pdf: Path, page_range) -> list[dict]:
    """Each table on the pages as a grid of cell texts (see :func:`cell_texts`;
    ``Table.extract()`` also flattens a cell's line breaks, losing which hyphen was
    a break, so it is used only to locate the cells)."""
    import pymupdf
    doc = pymupdf.open(str(pdf))
    out = []
    for p in page_range:
        page = doc[p - 1]
        for t in page.find_tables().tables:
            texts = iter(cell_texts(page, [c for row in t.rows for c in row.cells]))
            out.append({"page": p, "grid": [[(next(texts) or None) for _ in row.cells]
                                            for row in t.rows]})
    return out


def drug_pages(drugs: list[dict], pages_dir: Path = PAGES_DIR) -> list[tuple[str, list[int]]]:
    """Each roster drug's pages, a whole-word name match (reference pages included)."""
    texts = {int(p.stem): normalize_for_match(p.read_text("utf-8"))
             for p in pages_dir.glob("*.md")}
    out = []
    for d in drugs:
        name = d["name"] if isinstance(d["name"], str) else d["name"].get("en", "")
        needle = f" {normalize_for_match(name)} "
        hits = sorted(n for n, t in texts.items() if needle in f" {t} ")
        if hits:
            out.append((d["id"], hits))
    return out


INDEX_MARKER = "## Drug -> pages (generated by tools/fetch/fetch_agnp_tdm.py)"


def write_index_table(drugs: list[dict]) -> None:
    rows = drug_pages(drugs)
    body = [INDEX_MARKER, "",
            "Whole-word match of each roster drug's English name on every page "
            "(the reference list included, pages 99-130).", "",
            "| Drug | Pages |", "| --- | --- |"]
    body += [f"| {i} | {', '.join(map(str, p))} |" for i, p in rows]
    head = INDEX.read_text("utf-8").split(INDEX_MARKER)[0] if INDEX.exists() else ""
    INDEX.write_text(head.rstrip() + "\n\n" + "\n".join(body) + "\n", encoding="utf-8")


def main() -> int:
    argparse.ArgumentParser(description=__doc__.split("\n\n")[0]).parse_args()
    if not PDF.exists():
        raise SystemExit(f"PDF not found: {PDF.relative_to(ROOT)} (author-side)")
    drugs = drugs_io.load_drugs()
    index = roster_index(drugs)
    pages = PageGate({CORPUS: PAGES_DIR})

    ranges, skipped = therapeutic_ranges(table5_rows(read_grids(PDF, TABLE5_PAGES)),
                                         index, pages)
    t1 = table1_rows(read_grids(PDF, TABLE1_PAGES))
    enzymes = enzyme_confirmations(t1, index, pages)
    cache = {"ranges": dict(sorted(ranges.items())),
             "enzymes": dict(sorted(enzymes.items())),
             "table1_named": dict(sorted(table1_named(t1, index).items())),
             "skipped": skipped}
    atomic_write_json(CACHE_PATH, cache, indent=1)
    write_index_table(drugs)
    print(f"{len(ranges)} ranges ({sum('alert' in r for r in ranges.values())} with an "
          f"alert level), {len(skipped)} skipped, {len(enzymes)} drugs with Table 1 "
          f"enzyme quotes -> {CACHE_PATH.relative_to(ROOT)}")
    for s in skipped:
        print(f"  skip {s['drug']:<22} p{s['page']:<3} {s['why']}: {s['cell'][:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
