#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "beautifulsoup4>=4.12",
# ]
# ///
"""Fetch a drug's English Wikipedia page and extract its binding-affinity (Ki) table.

Why this exists: PDSP (corpus #5, tools/fetch/fetch_ki.py) is the primary source of
measured Ki, but it does not cover every drug/target (e.g. it drops subtype-less
"Alpha1", and newer or non-psychiatric agents are absent). Many drug articles on
Wikipedia carry a curated "Pharmacodynamics" binding table citing the primary
literature. This script mines that table so a Ki can be sourced even when PDSP has
none. It is deliberately author-side and additive; it never overrides a PDSP Ki
(see --apply in the companion applier once wired).

What it does (two halves, matching the TODO):
  1. STORE THE WHOLE PAGE. Fetch the rendered article via the MediaWiki action API,
     pinned to its current revision id, and write two author-side files under
     data_sources/wikipedia/ (gitignored, corpus #9 `wikipedia_pharm`):
       raw/<slug>.html   the verbatim rendered HTML (the "entire page", kept so we
                         can re-parse / mine other facts later without re-fetching)
       pages/<slug>.md   a plain-text rendering (headings + paragraphs + every table
                         flattened to "cell | cell | ..." rows). This is BOTH the
                         human-readable page AND the quote-gate page: a Ki source's
                         verbatim `quote` is one of these table rows, so
                         tools/check_data.py can confirm it verbatim exactly like a
                         book page (author-side; skipped on a clone lacking the tree).
     Both carry a header stamping the source URL, the revision id, the permanent
     ?oldid= link, and the fetch timestamp, so a citation pins an exact revision.
  2. EXTRACT THE Ki TABLE. Parse every wikitable, expand colspan/rowspan into a grid
     (Wikipedia affinity tables use multi-row headers), find the target column and
     the Ki column by fuzzy header matching, then read one Ki per row and map the
     target name to our target id. Adaptive by design: header wording, subscript
     spacing ("5-HT 1A"), tooltip noise ("SERT Tooltip ...") and footnotes vary, so
     matching is tolerant and every unresolved row/table is logged, not dropped
     silently, so the parser can be enhanced drug by drug (start: vortioxetine).

Reuses the PDSP mapping helpers (norm / parse_ki / NAME_PATTERNS) from fetch_ki.py
rather than re-deriving them; the target-name -> id resolution below only adds the
Wikipedia-specific bits (Greek letters, IUPHAR short codes, tooltip/footnote noise).

Usage (from the repo root; a uv-run script like pdf_to_pages.py, deps installed on demand):
    uv run tools/fetch/fetch_wikipedia_pharmacology.py --drug vortioxetine        # fetch + store + preview
    uv run tools/fetch/fetch_wikipedia_pharmacology.py --title Vortioxetine        # by explicit page title
    uv run tools/fetch/fetch_wikipedia_pharmacology.py --drug vortioxetine --json out.json
    uv run tools/fetch/fetch_wikipedia_pharmacology.py --drug vortioxetine --no-fetch   # re-parse the stored raw/

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import urllib.parse
import urllib.request

from bs4 import BeautifulSoup, Tag

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)          # sibling fetch_ki.py
import fetch_ki  # noqa: E402  (reuse norm / parse_ki / NAME_PATTERNS, no duplication)

DATA_DIR = os.path.join(REPO, "data_sources", "wikipedia")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PAGES_DIR = os.path.join(DATA_DIR, "pages")
META_PATH = os.path.join(REPO, "public", "data", "meta.json")
UA = "neurarium-dev/0.1 (brain-visualizer research; https://github.com/)"
API = "https://en.wikipedia.org/w/api.php"

# Greek letters Wikipedia uses in receptor names -> the latin token our ids use
# (α1A -> alpha1a, μ-opioid -> mu-opioid). Applied before normalization.
GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta",
    "κ": "kappa", "μ": "mu", "σ": "sigma", "ω": "omega",
}

# Wikipedia target names that do NOT map to a target id by a plain norm()-equality
# (full-word names, opioid letter codes, the 5-HT3A/5-HT3 mismatch, ...). Keys are
# already norm()-ed. Extend this as new drugs surface names the resolver misses.
WIKI_ALIASES = {
    "serotonintransporter": "sert", "sert": "sert",
    "norepinephrinetransporter": "net", "noradrenalinetransporter": "net", "net": "net",
    "dopaminetransporter": "dat", "dat": "dat",
    "5ht3a": "5ht3", "5ht3": "5ht3",
    "muopioid": "mu", "mopioid": "mu", "mor": "mu",
    "deltaopioid": "delta", "dopioid": "delta", "dor": "delta",
    "kappaopioid": "kappa", "kopioid": "kappa", "kor": "kappa",
    "nmda": "nmda", "sigma1": "sigma1", "sigmar1": "sigma1", "sigma": "sigma1",
    "vmat2": "vmat2", "cb1": "cb1",
}

# A subtype-less coarse name we deliberately DROP (no coarse id, exactly as PDSP
# drops subtype-less "Alpha1"): matched after the subtype patterns so α1A still wins.
DROP_NAMES = {"alpha1", "alpha1adrenergic", "alpha1adrenoceptor"}

FOOTNOTE_RE = re.compile(r"\[[^\]]*\]")          # [1], [note 2], [a]
TOOLTIP_RE = re.compile(r"\bTooltip\b.*$")       # "SERT Tooltip Serotonin transporter" -> "SERT"
WS_RE = re.compile(r"\s+")
# A Ki header: mentions Ki (and typically nM/affinity) but NOT the other constants.
KI_HEAD_RE = re.compile(r"\bk\s*i\b|\bki\b")
NOT_KI_RE = re.compile(r"ic50|ec50|\bkd\b|\bka\b|\bkb\b|ia\(|%\)")
TARGET_HEAD_RE = re.compile(r"target|site|receptor|protein|compound")


def slugify(title: str) -> str:
    """Filesystem slug for a page title (matches the ?title= form, lower-cased)."""
    return re.sub(r"[^a-z0-9]+", "_", title.strip().lower()).strip("_")


def clean_cell(text: str) -> str:
    """One table cell -> readable text: drop footnotes + tooltip tails, collapse WS."""
    text = TOOLTIP_RE.sub("", text)
    text = FOOTNOTE_RE.sub("", text)
    text = text.replace("\xa0", " ")
    return WS_RE.sub(" ", text).strip()


def greek_to_latin(s: str) -> str:
    for g, latin in GREEK.items():
        s = s.replace(g, latin)
    return s


def resolve_wiki_target(name: str, valid_ids: set[str]) -> str | None:
    """Map a Wikipedia target-cell name to our target id, or None (logged upstream).

    Order: exact norm()-equality against a real id (covers 5-HT1A, D2, H1, M1, SERT,
    α1A, NMDA, AMPA, ...), then the WIKI_ALIASES table, then the reused PDSP
    NAME_PATTERNS, then the explicit DROP set (subtype-less coarse names)."""
    base = greek_to_latin(name)
    # Drop trailing descriptor words so "5-HT1A receptor" / "β1-adrenergic" / "β1-adr."
    # reduce toward the bare code before matching.
    base = re.sub(r"(?i)\b(receptors?|adrenoceptors?|adrenergic|adr|opioid|"
                  r"transporter)\b\.?", " ", base)
    n = fetch_ki.norm(base)
    if not n:
        return None
    if n in DROP_NAMES:              # subtype-less coarse name we deliberately drop
        return None
    if n in valid_ids:
        return n
    if n in WIKI_ALIASES:
        return WIKI_ALIASES[n]
    for pat, tid in fetch_ki.NAME_PATTERNS:
        if pat.search(n) and tid in valid_ids:
            return tid
    # Last resort: a real id (>=4 chars, so no d2/h1/m1 false hits) is a clean prefix
    # of the normalized name ("beta1adr" -> beta1, "ampareceptor" -> ampa). Longest id
    # first so alpha2a wins over alpha2.
    for tid in sorted(valid_ids, key=len, reverse=True):
        nid = fetch_ki.norm(tid)
        if len(nid) >= 4 and n.startswith(nid):
            return tid
    return None


UNIT_UM_RE = re.compile(r"[µμ]m|\bum\b", re.I)      # micromolar -> x1000 to nM
NUM_RE = re.compile(r"[<>]?\s*(\d[\d.]*)")           # a number, optional </> prefix


def parse_ki_cell(raw: str):
    """A Ki cell -> {median,min,max,raw} in nM, or None if it holds no active value.

    Wikipedia affinity cells vary wildly: "1.6", a range "0.20-9.8 nM", commas
    "1,044", ceilings ">10,000 nM", µM units, and trailing species notes
    "148 nM (canine)". Strategy: strip notes/units/commas, pull every number, drop
    any >= 10 uM (fetch_ki.SENTINEL_NM, the "tested, inactive" ceiling, mirroring the
    PDSP filter), and summarize the remaining active numbers as median/min/max. None
    when nothing active survives (a purely ">10,000" / no-data cell)."""
    s = clean_cell(raw or "")
    s = re.sub(r"\([^)]*\)", " ", s)               # drop (rat)/(canine)/(HT29) notes
    s = s.replace(",", "").replace("≈", "").replace("~", "")
    if not s or s.strip() in {"-", "–", "—", "?", "ND", "n.d.", "N/A"}:
        return None
    factor = 1000.0 if UNIT_UM_RE.search(s) else 1.0
    nums = []
    for num in NUM_RE.findall(s):
        try:
            nums.append(float(num) * factor)
        except ValueError:
            continue
    active = [v for v in nums if v < fetch_ki.SENTINEL_NM]
    if not active:
        return None
    lo, hi = min(active), max(active)
    return {"median": round((lo + hi) / 2, 3) if lo != hi else round(lo, 3),
            "min": round(lo, 3), "max": round(hi, 3), "raw": clean_cell(raw or "")}


# --------------------------------------------------------------------------- #
# Fetch + store
# --------------------------------------------------------------------------- #

def fetch_page(title: str) -> dict:
    """Fetch the rendered article (action=parse) pinned to its current revision."""
    q = urllib.parse.urlencode({
        "action": "parse", "page": title, "prop": "text|revid|displaytitle",
        "format": "json", "redirects": 1, "formatversion": 2})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if "error" in data:
        raise SystemExit(f"Wikipedia API error for {title!r}: {data['error']}")
    p = data["parse"]
    real = p["title"]
    return {
        "title": real,
        "revid": p["revid"],
        "html": p["text"],
        "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(real.replace(' ', '_'))}",
        "oldid_url": f"https://en.wikipedia.org/w/index.php?oldid={p['revid']}",
        "fetched_at": datetime.datetime.now(datetime.timezone.utc)
                      .replace(microsecond=0).isoformat(),
    }


def row_text(tr: Tag) -> str:
    """One <tr> -> 'cell | cell | ...' (non-empty cells only). The single source of
    truth for a row's text, used BOTH for the stored page AND for a Ki source's
    verbatim quote, so a quote is guaranteed to appear in pages/<slug>.md."""
    cells = [clean_cell(c.get_text(" ", strip=True))
             for c in tr.find_all(["th", "td"])]
    return " | ".join(c for c in cells if c != "")


def table_to_text_rows(table: Tag) -> list[str]:
    """Flatten a table to text rows (for the page-text store)."""
    return [t for t in (row_text(tr) for tr in table.find_all("tr")) if t]


def render_page_text(soup: BeautifulSoup) -> str:
    """Full-page plain text: headings, paragraphs and every table as pipe-rows.

    This is the quote-gate page: a Ki source quote is one of the emitted table rows,
    so it is guaranteed to appear here verbatim (check_data confirms substring)."""
    body = soup.find("div", class_="mw-parser-output") or soup
    out: list[str] = []
    for el in body.find_all(["h2", "h3", "h4", "p", "table", "li"], recursive=True):
        if el.name in ("h2", "h3", "h4"):
            txt = clean_cell(el.get_text(" ", strip=True))
            if txt:
                out.append(("\n" + "#" * int(el.name[1]) + " " + txt))
        elif el.name in ("p", "li"):
            txt = clean_cell(el.get_text(" ", strip=True))
            if txt:
                out.append(("- " if el.name == "li" else "") + txt)
        elif el.name == "table":
            out.extend(table_to_text_rows(el))
    return "\n".join(out) + "\n"


def store_page(page: dict, page_text: str) -> tuple[str, str]:
    """Write raw/<slug>.html + pages/<slug>.md, both header-stamped. Returns paths."""
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(PAGES_DIR, exist_ok=True)
    slug = slugify(page["title"])
    header = (f"source: {page['url']}\nrevision: {page['revid']}\n"
              f"permalink: {page['oldid_url']}\nfetched_at: {page['fetched_at']}\n")
    raw_path = os.path.join(RAW_DIR, f"{slug}.html")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(f"<!--\n{header}-->\n{page['html']}")
    pages_path = os.path.join(PAGES_DIR, f"{slug}.md")
    with open(pages_path, "w", encoding="utf-8") as f:
        f.write(f"<!-- {page['title']} -->\n" + header.replace("\n", " | ") + "\n\n"
                + page_text)
    return raw_path, pages_path


# --------------------------------------------------------------------------- #
# Table grid + Ki extraction
# --------------------------------------------------------------------------- #

def grid_expand(table: Tag) -> list[list[dict]]:
    """Expand a table into a dense grid honouring rowspan/colspan.

    Returns a list of rows; each cell is {text, header} (header = came from a <th>).
    Standard HTML table model: a spanning cell fills the covered grid slots."""
    grid: list[list[dict | None]] = []
    for r, tr in enumerate(table.find_all("tr")):
        while len(grid) <= r:
            grid.append([])
        col = 0
        for cell in tr.find_all(["th", "td"], recursive=False):
            while col < len(grid[r]) and grid[r][col] is not None:
                col += 1
            try:
                rs = max(1, int(cell.get("rowspan", 1)))
                cs = max(1, int(cell.get("colspan", 1)))
            except (TypeError, ValueError):
                rs = cs = 1
            info = {"text": clean_cell(cell.get_text(" ", strip=True)),
                    "header": cell.name == "th"}
            for dr in range(rs):
                rr = r + dr
                while len(grid) <= rr:
                    grid.append([])
                row = grid[rr]
                while len(row) < col:
                    row.append(None)
                for dc in range(cs):
                    cc = col + dc
                    while len(row) <= cc:
                        row.append(None)
                    row[cc] = info if (dr == 0 and dc == 0) else dict(info)
            col += cs
    width = max((len(r) for r in grid), default=0)
    for row in grid:
        while len(row) < width:
            row.append({"text": "", "header": False})
        for i, c in enumerate(row):
            if c is None:
                row[i] = {"text": "", "header": False}
    return grid  # type: ignore[return-value]


def _header_split(grid: list[list[dict]]) -> tuple[int, list[str]]:
    """Return (num_header_rows, per-column stacked header label lower-cased)."""
    n_head = 0
    for row in grid:
        if row and all(c["header"] for c in row):
            n_head += 1
        else:
            break
    n_head = max(1, n_head)
    width = len(grid[0]) if grid else 0
    labels = []
    for c in range(width):
        parts = []
        for r in range(n_head):
            t = grid[r][c]["text"]
            if t and t not in parts:
                parts.append(t)
        labels.append(" ".join(parts).lower())
    return n_head, labels


def extract_from_table(table: Tag, valid_ids: set[str]) -> tuple[list[dict], list[str]]:
    """Pull (bindings, unresolved-row-notes) from one table, or ([], []) if not a Ki table."""
    grid = grid_expand(table)
    if len(grid) < 2:
        return [], []
    n_head, labels = _header_split(grid)
    ki_col = None
    for i, lab in enumerate(labels):
        if KI_HEAD_RE.search(lab) and not NOT_KI_RE.search(lab):
            ki_col = i
            break
    if ki_col is None:
        return [], []
    # Target column: an explicit "target/site/receptor" header, else column 0.
    tgt_col = 0
    for i, lab in enumerate(labels):
        if TARGET_HEAD_RE.search(lab):
            tgt_col = i
            break
    # grid row index r maps 1:1 to the r-th <tr>, so the quote comes from the raw
    # row (identical to the stored page text), not the span-expanded grid row.
    trs = table.find_all("tr")
    bindings, unresolved = [], []
    for r in range(n_head, len(grid)):
        row = grid[r]
        if len(row) <= max(ki_col, tgt_col):
            continue
        name = row[tgt_col]["text"]
        if not name:
            continue
        # Skip a spanned note/footer row: a full-width colspan cell fills the target
        # and Ki columns with the same prose ("Note: no significant activity at ..."),
        # and a real target name is a short code, never a sentence.
        if name == row[ki_col]["text"] or len(name) > 45:
            continue
        ki = parse_ki_cell(row[ki_col]["text"])
        if ki is None:
            continue
        tid = resolve_wiki_target(name, valid_ids)
        if tid is None:
            unresolved.append(f"{name!r} (Ki {ki['raw']})")
            continue
        bindings.append({
            "target": tid, "wiki_name": name, "ki": ki,
            "quote": row_text(trs[r]) if r < len(trs) else name,
        })
    return bindings, unresolved


def extract_bindings(soup: BeautifulSoup, valid_ids: set[str]) -> dict:
    """Scan every table; return the merged best Ki per target + diagnostics."""
    best: dict[str, dict] = {}
    unresolved_all: list[str] = []
    n_tables = 0
    for table in soup.find_all("table"):
        bindings, unresolved = extract_from_table(table, valid_ids)
        if bindings:
            n_tables += 1
        unresolved_all.extend(unresolved)
        for b in bindings:
            # Keep the strongest (lowest median) Ki if a target appears twice.
            cur = best.get(b["target"])
            if cur is None or b["ki"]["median"] < cur["ki"]["median"]:
                best[b["target"]] = b
    return {"bindings": best, "unresolved": unresolved_all, "n_ki_tables": n_tables}


# --------------------------------------------------------------------------- #

def load_valid_ids() -> set[str]:
    with open(META_PATH, encoding="utf-8") as f:
        return set(json.load(f)["drug_targets"].keys())


def drug_title(drug_id: str) -> str | None:
    """Best page title for a drug id: its Wikipedia URL leaf, else the id."""
    try:
        for d in fetch_ki.drugs_io.load_drugs():
            if d["id"] == drug_id:
                url = d.get("wikipedia") or ""
                if "/wiki/" in url:
                    return urllib.parse.unquote(url.rsplit("/wiki/", 1)[1])
                return d.get("name") or drug_id
    except Exception:
        pass
    return None


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drug", help="drug id (resolves its Wikipedia title)")
    ap.add_argument("--title", help="explicit Wikipedia page title (overrides --drug)")
    ap.add_argument("--no-fetch", action="store_true",
                    help="re-parse the stored raw/<slug>.html instead of fetching")
    ap.add_argument("--json", metavar="OUT", help="also write the extraction JSON here")
    args = ap.parse_args()

    title = args.title or (drug_title(args.drug) if args.drug else None)
    if not title:
        raise SystemExit("give --title <PageName> or --drug <id> with a wikipedia URL")
    valid_ids = load_valid_ids()

    if args.no_fetch:
        slug = slugify(title)
        raw_path = os.path.join(RAW_DIR, f"{slug}.html")
        if not os.path.exists(raw_path):
            raise SystemExit(f"no stored page at {raw_path}; run without --no-fetch first")
        with open(raw_path, encoding="utf-8") as f:
            html = f.read()
        page = {"title": title, "revid": "?", "url": "", "oldid_url": "",
                "fetched_at": "(stored)", "html": html}
        pages_path = os.path.join(PAGES_DIR, f"{slug}.md")
    else:
        page = fetch_page(title)
        soup0 = BeautifulSoup(page["html"], "html.parser")
        raw_path, pages_path = store_page(page, render_page_text(soup0))

    soup = BeautifulSoup(page["html"], "html.parser")
    res = extract_bindings(soup, valid_ids)

    slug = slugify(page["title"])
    out = {
        "drug": args.drug, "title": page["title"], "slug": slug,
        "revid": page["revid"], "url": page.get("oldid_url", ""),
        "raw": os.path.relpath(raw_path, REPO), "page": os.path.relpath(pages_path, REPO),
        "n_ki_tables": res["n_ki_tables"],
        "bindings": {tid: {"wiki_name": b["wiki_name"], "ki_nm": b["ki"],
                           "quote": b["quote"]}
                     for tid, b in sorted(res["bindings"].items())},
        "unresolved": res["unresolved"],
    }

    print(f"== {page['title']} (rev {page['revid']}) ==")
    print(f"stored: {out['raw']} + {out['page']}")
    print(f"Ki tables found: {res['n_ki_tables']}   targets resolved: {len(out['bindings'])}")
    for tid, b in out["bindings"].items():
        k = b["ki_nm"]
        rng = f" [{k['min']}-{k['max']}]" if k["min"] != k["max"] else ""
        print(f"  {tid:<10} {k['median']} nM{rng:<16}  <- {b['wiki_name']}")
    if res["unresolved"]:
        print("  unresolved rows (enhance the resolver):")
        for u in res["unresolved"]:
            print("    -", u)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print("wrote", args.json)


if __name__ == "__main__":
    main()
