#!/usr/bin/env python
"""Store each drug's US prescribing-label pharmacokinetics as corpus #14 (DailyMed).

The time-to-peak pass over the corpora already on disk (``fetch_tmax.py``) reaches a
third of the roster and no stored corpus reaches the rest: an English Wikipedia article
states a peak for 102 drugs, a Stahl monograph for 13, and 190 state it nowhere (see
``docs/SOURCING_GAPS.md``). **DailyMed** is what reaches those: the US National Library
of Medicine's archive of Structured Product Labels, free, no key, machine-readable, and
its section 12.3 (Pharmacokinetics) states a Tmax for essentially every oral drug
marketed in the US. Its limit is jurisdictional rather than technical: a drug never
marketed in the US (alpidem, several EU-only agents) has no SPL at all.

This is a **corpus fetcher**, not a claim pass: it states nothing, it only puts pages on
disk in the shape every other corpus uses, so ``fetch_tmax.py`` can offer their sentences
and ``apply_tmax.py`` can gate a quote against them exactly as it does a Wikipedia one.

What it stores, per drug:

* ``data_sources/dailymed/raw/<setid>.xml`` - the label SPL as downloaded, kept so the
  page can be re-derived without re-fetching.
* ``data_sources/dailymed/pages/<setid>.md`` - the quote-gate page: the text of the
  label's **pharmacokinetics** sections only (LOINC ``43682-4``, or ``34090-1`` Clinical
  Pharmacology on the older label format), one paragraph per line. Not the whole label:
  a Tmax sentence belongs there, and the rest of a 400 kB label is noise a reader would
  have to wade through to check a quote.
* ``tools/generated_cache/dailymed_labels.json`` - which label was chosen per drug
  (``setid``, title, version, publication date), so the choice is reviewable and the
  ``page`` field on a quote resolves back to a real public URL.

**Which label**, out of the dozens a common drug has (quetiapine has 207, mostly
repackagers reprinting one text): the search is by drug name, then titles naming a
modified-release or non-oral form are set aside, since those peak at a different time
than the plain tablet the simulation draws; candidates are tried in the API's own order
and the first whose pharmacokinetics section actually states a peak is kept. When the
filter leaves nothing (a drug sold only as a patch or a nasal spray), the unfiltered
candidates are tried rather than giving up: a real form's peak beats no peak.

Licence: SPL content is submitted by manufacturers and published by the NLM as a US
government work; DailyMed places no copyright restriction on it and asks for
attribution, which the corpus citation carries into every source tooltip.

Usage (from the repo root)::

    python tools/fetch/fetch_dailymed.py                  # only drugs with no tmax yet
    python tools/fetch/fetch_dailymed.py --all            # every roster drug
    python tools/fetch/fetch_dailymed.py --only zolpidem,codeine
    python tools/fetch/fetch_dailymed.py --refresh        # re-download stored labels

Network, polite (one request at a time, ``SLEEP`` seconds apart) and resumable: a drug
whose page is already on disk is skipped unless ``--refresh``. Stdlib only; author-side
(``data_sources/`` is gitignored).

Built with the help of Claude Code.
"""
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

ROOT = Path(__file__).resolve().parent.parent.parent           # repo root
sys.path.insert(0, str(ROOT / "tools"))

import drugs_io                                                 # noqa: E402

API = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
LABEL_URL = "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}"
RAW_DIR = ROOT / "data_sources" / "dailymed" / "raw"
PAGES_DIR = ROOT / "data_sources" / "dailymed" / "pages"
CACHE_PATH = ROOT / "tools" / "generated_cache" / "dailymed_labels.json"

USER_AGENT = "neurarium-dataset/1.0 (research dataset; contact via repository)"
SLEEP = 0.4          # seconds between requests, to stay a polite API citizen
SEARCH_PAGESIZE = 50
MAX_TRIES = 4        # labels downloaded per drug before giving up on it

# The sections a Tmax lives in. 43682-4 is section 12.3 of the modern PLR label;
# 34090-1 is the whole of Clinical Pharmacology on the older format, which has no
# separate pharmacokinetics code. Both are kept: a drug approved before 2006 only has
# the latter, and dropping it would lose exactly the older drugs Wikipedia also misses.
PK_SECTION_CODES = ("43682-4", "34090-1")

# A title naming a modified-release or non-oral form. Such a label states a real Tmax
# for a different product: Seroquel XR peaks around 6 h where the tablet peaks at 1.5 h,
# so mixing them would publish one formulation's number as the drug's.
NON_PLAIN_ORAL = re.compile(
    r"EXTENDED[ -]RELEASE|DELAYED[ -]RELEASE|MODIFIED[ -]RELEASE|CONTROLLED[ -]RELEASE|"
    r"\bER\b|\bXR\b|\bSR\b|\bLA\b|\bCD\b|\bODT\b|"
    r"INJECT|INTRAVENOUS|INTRAMUSCULAR|SUBCUTANEOUS|TRANSDERMAL|PATCH|IMPLANT|"
    r"SPRAY|INHAL|SUPPOSITORY|RECTAL|TOPICAL|CREAM|OINTMENT|GEL\b|PATCH", re.IGNORECASE)

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t ]+")


def _get(url: str, *, binary: bool = False):
    """One polite GET, returning decoded text (or bytes), or None on an HTTP error."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        print(f"  [warn] {url}: {e}", file=sys.stderr)
        return None
    finally:
        time.sleep(SLEEP)
    return raw if binary else raw.decode("utf-8", errors="replace")


def search(name: str) -> list[dict]:
    """The SPL summaries DailyMed returns for a drug name, newest-first as it sends them.

    Parameters
    ----------
    name
        The drug's name as the dataset spells it.

    Returns
    -------
    list of dict
        One ``{setid, title, spl_version, published_date}`` per label; empty when the
        drug has no US label at all (which is a real, expected answer here).
    """
    q = urllib.parse.urlencode({"drug_name": name, "pagesize": SEARCH_PAGESIZE})
    body = _get(f"{API}/spls.json?{q}")
    if not body:
        return []
    try:
        return json.loads(body).get("data", []) or []
    except json.JSONDecodeError:
        return []


def rank(candidates: list[dict], name: str) -> list[dict]:
    """Candidates worth downloading, plain-oral forms first, off-topic titles dropped.

    A title must name the drug (the search matches an active moiety, so a combination
    product comes back for either constituent and its label states the combination's
    kinetics, not this drug's).
    """
    key = re.sub(r"[^a-z]", "", name.lower())
    named = [c for c in candidates
             if key and key in re.sub(r"[^a-z]", "", (c.get("title") or "").lower())]
    plain = [c for c in named if not NON_PLAIN_ORAL.search(c.get("title") or "")]
    # The unfiltered ones stay as a fallback: a drug sold only as a nasal spray or a
    # patch has no plain-oral label, and its real form's peak is the honest answer.
    return plain + [c for c in named if c not in plain]


def section_texts(xml: str) -> list[str]:
    """The paragraph lines of the label's pharmacokinetics sections, in document order.

    The SPL is HL7 XML, so a section is located by its LOINC code and its text taken
    from the `<text>` element that follows. Tags are stripped rather than parsed into a
    tree: the page only has to be readable and quotable, and every table in an SPL is
    already prose-like once flattened.
    """
    out: list[str] = []
    for code in PK_SECTION_CODES:
        for m in re.finditer(rf'code\s+code="{code}"', xml):
            # The section body is the next <text>...</text> after the code element; a
            # section's own subsections are nested inside it, so one slice is enough.
            start = xml.find("<text>", m.end())
            if start < 0:
                continue
            end = xml.find("</text>", start)
            if end < 0:
                continue
            body = xml[start + len("<text>"):end]
            # A paragraph/table-row boundary becomes a line break, so one "line" of the
            # page is one checkable unit, exactly like the Wikipedia corpus.
            body = re.sub(r"</(paragraph|item|td|tr|title|caption)>", "\n", body)
            body = re.sub(r"<br\s*/?>", "\n", body)
            for line in _TAG.sub(" ", body).splitlines():
                line = _WS.sub(" ", html.unescape(line)).strip()
                if len(line) > 1:
                    out.append(line)
        if out:
            break            # 43682-4 found: no need for the coarser 34090-1 fallback
    return out


def page_text(meta: dict, lines: list[str]) -> str:
    """The stored page: a provenance header, then one pharmacokinetics line per line."""
    head = [
        f"# {meta['title']}",
        f"setid: {meta['setid']}",
        f"spl_version: {meta.get('spl_version')}",
        f"published: {meta.get('published_date')}",
        f"source: {LABEL_URL.format(setid=meta['setid'])}",
        f"fetched: {time.strftime('%Y-%m-%d')}",
        "",
    ]
    return "\n".join(head + lines) + "\n"


def has_peak(lines: list[str]) -> bool:
    """Whether any line names a peak AND carries a duration (what a Tmax needs).

    Reuses ``fetch_tmax``'s own matcher rather than restating it, so a label is kept
    exactly when the later worklist pass would find something to offer on it.
    """
    import fetch_tmax                                           # local: avoids a cycle
    return any(fetch_tmax.PEAK_RE.search(l) and fetch_tmax.durations_in(l)
               for l in lines)


def fetch_drug(drug: dict, *, refresh: bool, cache: dict) -> str:
    """Store one drug's label. Returns a one-word outcome for the run summary."""
    did = drug["id"]
    if not refresh and did in cache:
        page = PAGES_DIR / f"{cache[did]['setid']}.md"
        if page.exists():
            return "cached"
    name = drug.get("name") or did
    if "+" in name:
        return "combo"                 # a combination's label is not this drug's
    ranked = rank(search(name), name)
    if not ranked:
        return "no-label"
    tried = 0
    for cand in ranked:
        if tried >= MAX_TRIES:
            break
        setid = cand.get("setid")
        if not setid:
            continue
        raw_path = RAW_DIR / f"{setid}.xml"
        if refresh or not raw_path.exists():
            xml = _get(f"{API}/spls/{setid}.xml")
            tried += 1
            if not xml:
                continue
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(xml, encoding="utf-8")
        else:
            xml = raw_path.read_text(encoding="utf-8", errors="replace")
        lines = section_texts(xml)
        if not lines or not has_peak(lines):
            continue
        PAGES_DIR.mkdir(parents=True, exist_ok=True)
        (PAGES_DIR / f"{setid}.md").write_text(page_text(cand, lines), encoding="utf-8")
        cache[did] = {"setid": setid, "title": cand.get("title"),
                      "spl_version": cand.get("spl_version"),
                      "published_date": cand.get("published_date")}
        return "stored"
    return "no-peak"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated drug ids to scope the run to")
    ap.add_argument("--all", action="store_true",
                    help="every roster drug, not only those still lacking a tmax")
    ap.add_argument("--refresh", action="store_true",
                    help="re-download and re-pick even for a drug already stored")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after this many drugs (a smoke test)")
    args = ap.parse_args()
    only = {d.strip() for d in args.only.split(",") if d.strip()} if args.only else None

    cache = (json.loads(CACHE_PATH.read_text(encoding="utf-8"))
             if CACHE_PATH.exists() else {})
    drugs = drugs_io.load_drugs()
    todo = [d for d in drugs
            if (not only or d["id"] in only) and (args.all or only or not d.get("tmax"))]
    if args.limit:
        todo = todo[:args.limit]

    counts: dict[str, int] = {}
    for i, drug in enumerate(todo, 1):
        outcome = fetch_drug(drug, refresh=args.refresh, cache=cache)
        counts[outcome] = counts.get(outcome, 0) + 1
        print(f"[{i}/{len(todo)}] {drug['id']}: {outcome}", flush=True)
        if outcome == "stored":        # persist as we go: the run is long and resumable
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False,
                                             indent=1, sort_keys=True) + "\n",
                                  encoding="utf-8")
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1,
                                     sort_keys=True) + "\n", encoding="utf-8")
    print(f"[ok] {len(todo)} drug(s): "
          + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
          + f"; {len(cache)} label(s) in {CACHE_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
