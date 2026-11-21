#!/usr/bin/env python
"""Build the full-text paper corpus (#25 ``papers``) from PDFs the author holds.

Europe PMC (#17) only stores abstracts, plus full text when a paper is open access. A
review that matters (Monti 2011 on serotonin and sleep) is often neither, so the author
drops its PDF in ``data_sources/papers/pdf/<key>.pdf`` and lists it in :data:`PAPERS`.
This script splits each PDF into Markdown (``tools/fetch/pdf_to_pages.py``, run with
``uv``; ``--layout`` OCRs a PDF with no text layer) and writes ONE quote-gate page per
paper, ``data_sources/papers/pages/<key>.md``: a header (title, authors, journal, ``doi:``,
``pmid:``, ``source:``, ``fetched:`` = the PDF's own file date) then the text under one
``## PDF page N`` heading per page, so a quote can be found back in the PDF. ``page`` on a
quote is the key (``monti2011``) and links at ``https://doi.org/<doi>``
(``data_generators.page_links``).

Usage (repo root)::

    python tools/fetch/fetch_papers.py              # every listed paper with a PDF
    python tools/fetch/fetch_papers.py --only monti2011

Author-side and offline (the PDFs, like the books, are never committed). Built with the
help of Claude Code.
"""
from __future__ import annotations

import argparse
import datetime
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PDF_DIR = ROOT / "data_sources" / "papers" / "pdf"
PAGES_DIR = ROOT / "data_sources" / "papers" / "pages"

# key -> metadata. `ocr` = the PDF has no usable text layer (pdf_to_pages --layout).
PAPERS: dict[str, dict] = {
    "wichniak2017": {
        "title": "Effects of Antidepressants on Sleep",
        "authors": "Wichniak A, Wierzbicka A, Walęcka M, Jernajczyk W.",
        "journal": "Current Psychiatry Reports 19(9):63, 2017",
        "doi": "10.1007/s11920-017-0816-4", "pmid": "28791566"},
    "bates2026": {
        "title": "Pharmacological Interventions and Their Effects on Total Sleep, Slow Wave "
                 "Sleep, and REM Sleep: A Scoping Review of Current Evidence",
        "authors": "Bates J, Krall T, Kelbert J, Lau C, Tobin J, Lee-Iannotti J.",
        "journal": "Observations and Insights in Pulmonary and Critical Care 1(3), 2026",
        "doi": "10.2458/001c.161875", "pmid": None},
    "watson2010": {
        "title": "Neuropharmacology of Sleep and Wakefulness",
        "authors": "Watson CJ, Baghdoyan HA, Lydic R.",
        "journal": "Sleep Medicine Clinics 5(4):513-528, 2010",
        "doi": "10.1016/j.jsmc.2010.08.003", "pmid": "21278831"},
    "zilles2009": {
        "title": "Receptor mapping: architecture of the human cerebral cortex",
        "authors": "Zilles K, Amunts K.",
        "journal": "Current Opinion in Neurology 22(4):331-339, 2009",
        "doi": "10.1097/WCO.0b013e32832d95db", "pmid": "19512925"},
    "monti2011": {
        "title": "Serotonin control of sleep-wake behavior",
        "authors": "Monti JM.",
        "journal": "Sleep Medicine Reviews 15(4):269-281, 2011",
        "doi": "10.1016/j.smrv.2010.11.003", "pmid": "21459634", "ocr": True},
}


def split_pdf(pdf: Path, ocr: bool) -> list[str]:
    """The PDF's pages as Markdown, in order (pdf_to_pages.py into a scratch dir)."""
    with tempfile.TemporaryDirectory() as tmp:
        cmd = ["uv", "run", str(ROOT / "tools" / "fetch" / "pdf_to_pages.py"),
               "--pdf", str(pdf), "--out", tmp] + (["--layout"] if ocr else [])
        subprocess.run(cmd, check=True, cwd=ROOT, capture_output=True)
        files = sorted(Path(tmp).glob("*.md"), key=lambda p: int(p.stem))
        return [f.read_text(encoding="utf-8") for f in files]


def page_text(key: str, meta: dict, pages: list[str], fetched: str) -> str:
    head = [f"# {meta['title']}", f"authors: {meta['authors']}",
            f"journal: {meta['journal']}", f"doi: {meta['doi']}"]
    if meta.get("pmid"):
        head.append(f"pmid: {meta['pmid']}")
    head += [f"source: https://doi.org/{meta['doi']}", f"key: {key}", f"fetched: {fetched}", ""]
    body = []
    for n, text in enumerate(pages, 1):
        body += [f"## PDF page {n}", "", text.strip(), ""]
    return "\n".join(head + body)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", help="comma-separated paper keys")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    for key, meta in PAPERS.items():
        if only and key not in only:
            continue
        pdf = PDF_DIR / f"{key}.pdf"
        if not pdf.exists():
            print(f"[skip] {key}: no {pdf.relative_to(ROOT)}")
            continue
        fetched = datetime.date.fromtimestamp(pdf.stat().st_mtime).isoformat()
        pages = split_pdf(pdf, bool(meta.get("ocr")))
        (PAGES_DIR / f"{key}.md").write_text(page_text(key, meta, pages, fetched),
                                             encoding="utf-8")
        print(f"[ok] {key}: {len(pages)} page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
