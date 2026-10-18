#!/usr/bin/env python
"""Apply each drug's current marketing-authorisation holders (kind ``drug_holders``).

Code-read, no model in between (``extraction: "code"``, no judge, no ``recheck_quotes.py``
run): ONE node per (drug, market), off a regulator register already stored author-side.

* ``us``: the sponsor of the application the Drugs@FDA pass picked
  (``tools/generated_cache/drugsfda_approvals.json``, status ``found``), read off the
  title line of its page ``data_sources/drugsfda/pages/<NDA>.md``
  (``# Drugs@FDA application NDA020639 (CHEPLAPHARM)``). The quote is that title minus
  its ``# ``; ``page`` the NDA. Used whatever source the first approval itself won from
  (``history.earliest_wins``), since the holder is a fact of that NDA. A title reading
  "sponsor not stated" publishes nothing.
* ``fr``: the ``holder:`` header line of every brand-name product page the BDPM pass
  stored (``tools/generated_cache/bdpm_labels.json`` ``brands[].cis`` ->
  ``data_sources/bdpm/pages/<cis>.md``). Distinct holders fold into one node's
  ``names`` (buprenorphine: Temgesic, Subutex, Orobupre are three companies), each with
  its own quote; ``page`` the CIS.

Gates, re-derived from the pages, never trusted: the name is non-empty and a verbatim
substring of its quote, and the quote is verbatim on its page (``pipeline.gate.PageGate``).
Sole writer of ``holders``, idempotent: every drug's holders are rebuilt from the current
caches on each run.

    python tools/sourcing/apply_drug_holders.py --dry-run
    python tools/sourcing/apply_drug_holders.py

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
from lib import drugs_io  # noqa: E402
from data_generators import origin  # noqa: E402
from pipeline.gate import PageGate  # noqa: E402 (the applier's page gate)
import fetch_drugsfda as fda  # noqa: E402
from lib.corpora import bdpm  # noqa: E402

FDA_TITLE_RE = re.compile(r"^# (Drugs@FDA application (\S+) \((.+)\))\s*$")
BDPM_HOLDER_RE = re.compile(r"^(holder:\s*(.+?))\s*$")
NO_SPONSOR = "sponsor not stated"
PAGES = {"drugsfda": fda.PAGES_DIR, "bdpm": bdpm.PAGES_DIR}


def _read(path: Path) -> str | None:
    return path.read_text("utf-8", errors="replace") if path.exists() else None


def us_holder(rec: dict, pages_dir: Path) -> tuple[str, str, str] | None:
    """``(name, quote, page)`` for one Drugs@FDA cache record, or None."""
    if rec.get("status") != "found" or not rec.get("application"):
        return None
    text = _read(pages_dir / f"{rec['application']}.md")
    m = FDA_TITLE_RE.match((text or "").split("\n", 1)[0])
    if not m or m.group(2) != rec["application"] or m.group(3) == NO_SPONSOR:
        return None
    return m.group(3), m.group(1), rec["application"]


def fr_holders(rec: dict, pages_dir: Path) -> list[tuple[str, str, str]]:
    """``(name, quote, page)`` per distinct holder of the drug's BDPM brand products."""
    out, seen = [], set()
    for brand in rec.get("brands") or []:
        text = _read(pages_dir / f"{brand['cis']}.md") or ""
        for line in text.splitlines():
            m = BDPM_HOLDER_RE.match(line)
            if m:
                if m.group(2) not in seen:
                    seen.add(m.group(2))
                    out.append((m.group(2), m.group(1), brand["cis"]))
                break
            if not line.strip():
                break  # the header block ends at the first blank line
    return out


def gate(market: str, found: list[tuple[str, str, str]], pages: PageGate) -> dict | None:
    """The holder node for one market, keeping only names whose quote passes."""
    corpus = "drugsfda" if market == "us" else "bdpm"
    names, sources = [], []
    for name, quote, page in found:
        if not name or name not in quote or not pages.on_page(corpus, page, quote):
            continue
        names.append(name)
        sources.append({"corpus": corpus, "page": page, "quote": quote,
                        "provenance": "verified", "extraction": "code"})
    return {"market": market, "names": names, "sources": sources} if names else None


def apply(fda_cache: dict, bdpm_cache: dict, drugs: list[dict], pages: PageGate,
          dirs: dict[str, Path] = PAGES) -> dict[str, int]:
    """Rebuild every drug's ``holders`` in place; return the per-market counts."""
    counts = {m: 0 for m in origin.HOLDER_MARKETS}
    for drug in drugs:
        drug.pop("holders", None)
        us = us_holder(fda_cache.get(drug["id"]) or {}, dirs["drugsfda"])
        found = {"us": [us] if us else [],
                 "fr": fr_holders(bdpm_cache.get(drug["id"]) or {}, dirs["bdpm"])}
        rows = [r for r in (gate(m, found[m], pages) for m in origin.HOLDER_MARKETS) if r]
        if rows:
            drug["holders"] = rows
            for r in rows:
                counts[r["market"]] += 1
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not (fda.PAGES_DIR.is_dir() and bdpm.PAGES_DIR.is_dir()):
        print("[error] data_sources/drugsfda/pages or data_sources/bdpm/pages absent: run "
              "fetch_drugsfda.py and fetch_bdpm.py first.", file=sys.stderr)
        return 1
    fda_cache = json.loads(fda.CACHE_PATH.read_text("utf-8"))["drugs"]
    bdpm_cache = json.loads(bdpm.CACHE_PATH.read_text("utf-8"))
    drugs = drugs_io.load_drugs()
    counts = apply(fda_cache, bdpm_cache, drugs, PageGate(PAGES))
    tag = "[dry-run] " if args.dry_run else ""
    print(f"{tag}holders: " + ", ".join(f"{m} {n} drugs" for m, n in counts.items()))
    if not args.dry_run:
        drugs_io.save_drugs(drugs)
        print(f"wrote {drugs_io.DRUGS_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
