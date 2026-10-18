#!/usr/bin/env python
"""Fetch Drugs@FDA (corpus #18 ``drugsfda``) and find each drug's first US approval.

Drugs@FDA is the FDA's own register of every approved application. Its one export we
read is openFDA's bulk ``drug/drugsfda`` JSON (public domain, ~9 MB zipped, one record
per application with its products, active ingredients and submission history):
www.fda.gov itself refuses scripted downloads, download.open.fda.gov does not.

Per roster drug the pass is pure code, no model and no judge (``extraction: "code"``):

1. every **NDA** whose products include one with the drug as its **only** active
   ingredient (an ANDA is a generic copy, never the first approval; a BLA is a
   biologic; a combination product is another drug). The ingredient joins after the
   salt / hydrate words are dropped (``SERTRALINE HYDROCHLORIDE`` -> sertraline), via
   ``FDA_NAMES`` for a US name that differs from ours (pethidine is ``MEPERIDINE``), and
   stereo-aware through ``tools/chirality.py``;
2. each such NDA's original approval: its ``ORIG`` submission with status ``AP``
   (tentative ``TA`` never counts);
3. the earliest one. **Unless** a matching NDA has no ``ORIG`` approval at all: Drugs@FDA
   holds no approval date for an application approved before 1982, so the earliest
   *dated* one would be a later reformulation and the year would lie. Such a drug gets
   nothing (``undated``), never a placeholder;
4. and only when that NDA's own FDA class lets it be the moiety's first approval
   (:func:`first_of_moiety`), else ``superseded``: the export misses some old
   applications, and a "new dosage form" NDA says an earlier one exists.

The chosen application's page is written to ``data_sources/drugsfda/pages/<appl>.md``
(author-side, gitignored): a provenance header stamped ``fetched:`` with the export's
download date, then one flattened row per product, ``application | brand | active
ingredient | dosage form | ORIG approved <date>``. That row is the quote.
``tools/generated_cache/drugsfda_approvals.json`` keeps the per-drug result (and why a
drug got none), read by ``tools/sourcing/apply_drugsfda.py``, the sole writer.

Usage (from the repo root)::

    python tools/fetch/fetch_drugsfda.py              # reuse the stored export
    python tools/fetch/fetch_drugsfda.py --refresh    # re-download it first

Stdlib only. Licence: openFDA data is public domain (CC0); the corpus citation names the
source anyway.

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from lib import polite_http  # noqa: E402 (the one polite GET + User-Agent)
from lib import chirality  # noqa: E402
from lib.io_atomic import atomic_write_json  # noqa: E402
from lib import drugs_io  # noqa: E402
from lib import salt_words  # noqa: E402

EXPORT_URL = "https://download.open.fda.gov/drug/drugsfda/drug-drugsfda-0001-of-0001.json.zip"
BASE = ROOT / "data_sources" / "drugsfda"
EXPORT = BASE / "raw" / "drug-drugsfda-0001-of-0001.json.zip"
PAGES_DIR = BASE / "pages"
CACHE_PATH = ROOT / "tools" / "generated_cache" / "drugsfda_approvals.json"
APP_URL = ("https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm"
           "?event=overview.process&ApplNo={num}")

# Counter-ion, hydrate and ester words around the moiety, dropped before the join (the
# shared English list, see ``tools/salt_words.py``), folded to this module's lower case.
SALT_WORDS = frozenset(w.lower() for w in salt_words.EN_SALT_WORDS)

# Our drug id -> the US (USAN / FDA) name(s), when the roster's name is not it.
FDA_NAMES: dict[str, list[str]] = {
    "pethidine": ["meperidine"],
    "amphetamine_d": ["dextroamphetamine"],
    "amphetamine_dl": ["amphetamine"],
    "methylphenidate_d": ["dexmethylphenidate"],
    "methylphenidate_dl": ["methylphenidate"],
    "valproate": ["valproic acid", "divalproex", "valproate"],
    "thc": ["dronabinol"],
    "triiodothyronine": ["liothyronine"],
}


# A roster combination ("Naltrexone + Bupropion", "Phentermine–Topiramate"): its
# approval is a combination product's, which the single-ingredient join never reads.
COMBO_RE = re.compile(r"[/+–]")


def _words(name: str) -> str:
    """``"SERTRALINE HYDROCHLORIDE"`` -> ``"sertraline"``: lower-cased, salt words out."""
    toks = re.findall(r"[a-z0-9]+", name.lower())
    return " ".join(t for t in toks if t not in SALT_WORDS)


def drug_keys(drug: dict) -> set[str]:
    """The folded names an FDA ingredient may carry for ``drug``."""
    names = FDA_NAMES.get(drug["id"]) or [drug.get("name") or drug["id"]]
    return {_words(n) for n in names if _words(n)}


def ingredient_key(name: str, drug_id: str) -> str | None:
    """The folded moiety of one FDA ingredient, or None when its stereo tag excludes
    ``drug_id`` (a ``(-)``-tagged row never counts as a racemate we model)."""
    stem, tag = chirality.split_stereo(name)
    return _words(stem) if chirality.tag_allowed(tag, drug_id) else None


def _date(s: str) -> str:
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def _orig(app: dict) -> dict | None:
    """The application's earliest approved ``ORIG`` submission, or None."""
    subs = [s for s in app.get("submissions") or []
            if s.get("submission_type") == "ORIG" and s.get("submission_status") == "AP"
            and s.get("submission_status_date")]
    return min(subs, key=lambda s: s["submission_status_date"]) if subs else None


def orig_approval(app: dict) -> str | None:
    """The application's original approval date (``YYYY-MM-DD``), or None."""
    sub = _orig(app)
    return _date(sub["submission_status_date"]) if sub else None


def first_of_moiety(app: dict) -> bool:
    """Whether the application's own class allows it to be the moiety's first approval.

    FDA classes an NDA against what was approved before it: only Type 1 (new molecular
    entity) is a first. Type 2 (new active ingredient: a new salt, ester or enantiomer
    of a previously approved moiety) and Type 3 / 5 (new dosage form / formulation) say
    an earlier approval of the moiety exists (secobarbital's 1950 Type 2 NDA, while
    Seconal predates 1938), and Type 7 says it was sold before any approval (codeine,
    2009). The export misses some old applications (OxyContin's
    NDA020553 is absent, so oxycodone's earliest *listed* NDA is a 1998 reformulation),
    so such a class means the real first approval is out of reach. Pre-1980s records
    carry no class (``UNKNOWN`` or none) and are taken at their date.
    """
    sub = _orig(app) or {}
    cls = sub.get("submission_class_code_description") or sub.get("submission_class_code")
    return cls in (None, "", "UNKNOWN") or cls.startswith("Type 1 ")


def matching_products(app: dict, drug: dict) -> list[dict]:
    """``app``'s single-ingredient products whose ingredient is ``drug``."""
    keys = drug_keys(drug)
    out = []
    for p in app.get("products") or []:
        ais = p.get("active_ingredients") or []
        if len(ais) == 1 and ingredient_key(ais[0].get("name") or "", drug["id"]) in keys:
            out.append(p)
    return out


def row(app: dict, product: dict, date: str) -> str:
    """The flattened quote row of one product."""
    return " | ".join([app["application_number"], product.get("brand_name") or "",
                       product["active_ingredients"][0]["name"],
                       product.get("dosage_form") or "", f"ORIG approved {date}"])


def first_approval(drug: dict, apps: list[dict]) -> dict:
    """``{status, ...}`` for one drug: ``found`` with the earliest NDA, ``undated`` when a
    matching NDA predates Drugs@FDA's dates, ``superseded`` when the earliest one says
    an earlier approval exists, ``combo`` / ``none`` otherwise."""
    if COMBO_RE.search(drug.get("name") or ""):
        return {"status": "combo"}
    hits = []
    for app in apps:
        if not app["application_number"].startswith("NDA"):
            continue
        prods = matching_products(app, drug)
        if prods:
            hits.append((orig_approval(app), app, prods))
    if not hits:
        return {"status": "none"}
    undated = [a["application_number"] for d, a, _ in hits if d is None]
    if undated:
        return {"status": "undated", "applications": sorted(undated)}
    date, app, prods = min(hits, key=lambda h: (h[0], h[1]["application_number"]))
    if not first_of_moiety(app):
        sub = _orig(app)
        return {"status": "superseded", "application": app["application_number"],
                "date": date, "class": sub.get("submission_class_code_description")
                or sub.get("submission_class_code")}
    return {"status": "found", "application": app["application_number"], "date": date,
            "year": int(date[:4]), "quote": row(app, prods[0], date),
            "applications": len(hits)}


def page_text(app: dict, date: str, export_date: str, fetched: str) -> str:
    """The quote-gate page of one application: header, then one row per product."""
    num = app["application_number"][3:]
    head = [f"# Drugs@FDA application {app['application_number']}"
            f" ({app.get('sponsor_name') or 'sponsor not stated'})",
            f"application: {app['application_number']}",
            f"source: {APP_URL.format(num=num)}",
            f"export: openFDA drug/drugsfda bulk export, last_updated {export_date}",
            f"fetched: {fetched}", ""]
    rows = []
    for p in app.get("products") or []:
        if len(p.get("active_ingredients") or []) == 1:
            r = row(app, p, date)
            if r not in rows:
                rows.append(r)
    return "\n".join(head + rows) + "\n"


def download() -> None:
    EXPORT.parent.mkdir(parents=True, exist_ok=True)
    req = polite_http.request(EXPORT_URL)
    with urllib.request.urlopen(req, timeout=300) as r, open(EXPORT, "wb") as fh:
        fh.write(r.read())


def load_export() -> tuple[list[dict], str]:
    """``(applications, the export's last_updated date)``."""
    with zipfile.ZipFile(EXPORT) as z:
        data = json.loads(z.read(z.namelist()[0]))
    return data["results"], data["meta"]["last_updated"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="re-download the export")
    args = ap.parse_args()
    if args.refresh or not EXPORT.exists():
        download()
    apps, export_date = load_export()
    fetched = _dt.date.fromtimestamp(os.path.getmtime(EXPORT)).isoformat()
    by_num = {a["application_number"]: a for a in apps}
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    out, counts = {}, {}
    for drug in drugs_io.load_drugs():
        rec = first_approval(drug, apps)
        out[drug["id"]] = rec
        counts[rec["status"]] = counts.get(rec["status"], 0) + 1
        if rec["status"] == "found":
            app = by_num[rec["application"]]
            (PAGES_DIR / f"{rec['application']}.md").write_text(
                page_text(app, rec["date"], export_date, fetched), encoding="utf-8")
    keep = {f"{r['application']}.md" for r in out.values() if r["status"] == "found"}
    for stale in PAGES_DIR.glob("*.md"):
        if stale.name not in keep:      # a drug no longer found: its page is not cited
            stale.unlink()
    atomic_write_json(CACHE_PATH, {"export_last_updated": export_date, "drugs": out},
                      indent=1, sort_keys=True)
    print(f"{len(apps)} applications (export {export_date}); per drug: "
          + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
          + f" -> {CACHE_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
