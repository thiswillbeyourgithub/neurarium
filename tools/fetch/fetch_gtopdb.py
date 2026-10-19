#!/usr/bin/env python
"""Fetch IUPHAR/BPS Guide to Pharmacology (GtoPdb) tissue-distribution statements
for the dataset's receptors, to source their expression-region ("Found in") nodes.

Each receptor's expression regions are separately-graded nodes (kind
``receptor_locations``); today they are all ``llm``. GtoPdb publishes, per target, a
"Tissue Distribution" list: a verbatim tissue sentence + assay technique + **species**
+ a PubMed id. This tool caches that list author-side and emits a **worklist** pairing
each receptor's *existing* region list (confirm-only: we never add/drop regions) with
its candidate tissue quotes, for a downstream judge to match a region to a quote.

It is the GtoPdb analogue of ``build_source_worklist.py``: network, polite, idempotent
(re-run only refetches missing targets unless ``--refresh``). Nothing here writes into
``generate_data.py``; a separate apply step turns judged matches into
``RECEPTOR_LOCATION_SOURCES`` entries.

Outputs (author-side, under the gitignored ``data_sources/gtopdb/``):
- ``raw/<receptor_id>.json`` : the raw GtoPdb tissueDistribution response (reference).
- ``pages/<targetId>.md``    : the cleaned tissue strings, one per line. This is the
  corpus "page" the ``gtopdb`` SOURCE_CORPORA entry points at, so ``check_data.py``'s
  verbatim-quote gate confirms each stored quote is present here (a stored quote is
  one of these lines).
- ``worklist.json``          : ``[{receptor_id, gene, target_id, regions:[bases],
  candidates:[{quote, species, pmid, technique}]}]`` for the judge.

The GtoPdb contents are CC BY-SA 4.0 (the licence the project already attributes for
Wikipedia text/molecule images). Run from the repo root::

    python tools/fetch/fetch_gtopdb.py            # fetch all mapped receptors, write worklist
    python tools/fetch/fetch_gtopdb.py --only 5ht2a,d2
    python tools/fetch/fetch_gtopdb.py --refresh  # refetch even cached targets

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent   # script lives in tools/fetch/
sys.path.insert(0, str(REPO / "tools"))
from lib.page_file import page_path  # noqa: E402 (refuses a path-like page)
from lib import polite_http  # noqa: E402 (the one polite GET + User-Agent)
from lib.gene_maps import RECEPTOR_GENES  # noqa: E402
OUT = REPO / "data_sources" / "gtopdb"
RAW = OUT / "raw"
PAGES = OUT / "pages"
WORKLIST = OUT / "worklist.json"
RECEPTORS_JSONL = REPO / "public" / "data" / "receptors.jsonl"
BASE = "https://www.guidetopharmacology.org/services"
DELAY_S = 1.0  # polite gap between requests


# GtoPdb's web services need a per-user API key since 2026-09 (an anonymous call
# answers 401 "API key is missing"). Their REST page recommends the request
# header, which keeps the key out of every URL we could print or store.
API_KEY_ENV = "GTOPDB_API_KEY"
API_KEY_FILE = OUT / "api_key.txt"
API_KEY_HEADER = "GTP-API-Key"


def api_key() -> str:
    """The GtoPdb API key: env ``GTOPDB_API_KEY``, else ``data_sources/gtopdb/api_key.txt``.

    Never printed, logged or written anywhere: it only rides the request header."""
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key and API_KEY_FILE.exists():
        key = API_KEY_FILE.read_text(encoding="utf-8").strip()
    if not key:
        raise SystemExit(
            f"error: no GtoPdb API key: set env {API_KEY_ENV} or put the key in "
            f"{API_KEY_FILE.relative_to(REPO)} (request one from your "
            f"guidetopharmacology.org account)")
    return key


def _backoff_s(exc: urllib.error.HTTPError, attempt: int) -> float:
    """Seconds to wait after a 429: the server's ``Retry-After`` when it sends one,
    else a doubling pause (10, 20, 40 s ...). The keyed API rate-limits a burst."""
    retry_after = (exc.headers or {}).get("Retry-After", "") if exc.headers else ""
    return float(retry_after) if str(retry_after).isdigit() else 10.0 * 2 ** attempt


def http_json(url: str, tries: int = 6):
    """GET a JSON URL politely, with retries (a 429 backs off). Returns parsed JSON."""
    headers = {"User-Agent": polite_http.USER_AGENT, "Accept": "application/json", API_KEY_HEADER: api_key()}
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            time.sleep(DELAY_S)
            return data
        except urllib.error.HTTPError as exc:  # noqa: PERF203
            if exc.code in (401, 403):
                raise SystemExit(f"error: GtoPdb refused the API key ({exc.code}) for {url}; "
                                 f"check {API_KEY_ENV} / {API_KEY_FILE.relative_to(REPO)}") from None
            last = exc
            time.sleep(_backoff_s(exc, attempt) if exc.code == 429 else 1.0 + attempt)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:  # noqa: PERF203
            last = exc
            time.sleep(1.0 + attempt)
    raise SystemExit(f"error: failed to fetch {url}: {last}")


def file_date(path: Path) -> str:
    """A file's modification date (YYYY-MM-DD), the download date of an unstamped cache."""
    return time.strftime("%Y-%m-%d", time.localtime(path.stat().st_mtime))


def clean(text: str) -> str:
    """Strip GtoPdb's inline HTML (<i>, <sub>, ...) + unescape entities + collapse
    whitespace, so the stored quote and the cached page line are the same plain text
    (and thus pass the verbatim-quote gate identically)."""
    text = re.sub(r"<[^>]+>", "", text or "")
    return " ".join(html.unescape(text).split())


def resolve_target(gene: str) -> dict | None:
    """Resolve an HGNC gene symbol to a GtoPdb target ({targetId, name}) or None."""
    hits = http_json(f"{BASE}/targets?geneSymbol={urllib.parse.quote(gene)}")
    if not hits:
        return None
    return {"target_id": hits[0]["targetId"], "name": clean(hits[0].get("name", ""))}


def load_receptor_regions() -> dict[str, list[str]]:
    """base region ids each receptor lists today (confirm-only works over these)."""
    out: dict[str, list[str]] = {}
    for line in RECEPTORS_JSONL.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        bases = sorted({re.sub(r"_(L|R)$", "", s) for s in rec.get("locations", [])})
        out[rec["id"]] = bases
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="comma-separated receptor ids to fetch (default all)")
    ap.add_argument("--refresh", action="store_true",
                    help="refetch targets even if their raw cache exists")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    PAGES.mkdir(parents=True, exist_ok=True)
    regions_by_receptor = load_receptor_regions()

    want = list(RECEPTOR_GENES)
    if args.only:
        want = [r.strip() for r in args.only.split(",") if r.strip()]
        unknown = [r for r in want if r not in RECEPTOR_GENES]
        if unknown:
            raise SystemExit(f"error: unmapped receptor ids: {unknown}")

    worklist = []
    n_no_data = 0
    for rid in want:
        gene = RECEPTOR_GENES[rid]
        raw_path = page_path(RAW, rid, ".json")
        if raw_path.exists() and not args.refresh:
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
        else:
            tgt = resolve_target(gene)
            if tgt is None:
                print(f"  [miss] {rid} ({gene}): no GtoPdb target", file=sys.stderr)
                continue
            entries = http_json(
                f"{BASE}/targets/{tgt['target_id']}/tissueDistribution")
            payload = {"receptor_id": rid, "gene": gene,
                       "target_id": tgt["target_id"], "target_name": tgt["name"],
                       "entries": entries or [],
                       "fetched": time.strftime("%Y-%m-%d")}
            raw_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        entries = payload.get("entries", [])
        # Write the corpus page: every cleaned tissue string on its own line, so a
        # stored quote (one such string) is a verbatim substring of pages/<id>.md.
        # The header stamps the download date (data_generators/freshness.py reads it);
        # a raw cache from before stamping falls back to its own file date.
        lines = [clean(e.get("tissue", "")) for e in entries if e.get("tissue")]
        page = page_path(PAGES, payload['target_id'])
        page.write_text(f"fetched: {payload.get('fetched') or file_date(raw_path)}\n"
                        + "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

        candidates = []
        for e in entries:
            tissue = clean(e.get("tissue", ""))
            if not tissue:
                continue
            pmid = None
            refs = e.get("refs") or []
            if refs:
                pmid = refs[0].get("pmid")
            candidates.append({
                "quote": tissue,
                "species": e.get("species"),
                "technique": clean(e.get("technique", "")),
                "pmid": pmid,
            })
        if not candidates:
            n_no_data += 1
        worklist.append({
            "receptor_id": rid,
            "gene": gene,
            "target_id": payload["target_id"],
            "regions": regions_by_receptor.get(rid, []),
            "candidates": candidates,
        })
        print(f"  [ok]   {rid:10s} ({gene:8s}) target {payload['target_id']}: "
              f"{len(candidates)} tissue entries, {len(regions_by_receptor.get(rid, []))} regions")

    WORKLIST.write_text(json.dumps(worklist, indent=2), encoding="utf-8")
    with_data = sum(1 for w in worklist if w["candidates"])
    print(f"\nwrote {WORKLIST.relative_to(REPO)}: {len(worklist)} receptors "
          f"({with_data} with tissue data, {n_no_data} empty)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
