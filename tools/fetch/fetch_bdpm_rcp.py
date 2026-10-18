#!/usr/bin/env python
"""Store the French RCP sections 4.2 / 4.3 / 4.4 per drug: corpus #24 (``bdpm_rcp``).

The same official text as corpus #16 (``bdpm``, ANSM's public drug database, Licence
Ouverte), read for a different question: what the label asks a prescriber to check
BEFORE starting the drug (the "bilan pre-therapeutique") and while it is taken. Those
asks live in 4.3 (contre-indications), 4.4 (mises en garde speciales et precautions
d'emploi) and sometimes 4.2 (posologie), never in 5.2, so the #16 pages (5.2 only) do
not hold them.

A **corpus fetcher, offline for every drug with a French product**: the RCP HTML is
already on disk in three places, and the freshest copy of each product wins:

* ``data_sources/bdpm/raw/<cis>.html``: the page ``fetch_bdpm.py`` downloaded (about
  116 products), dated by the file's mtime (the download time);
* ``../justelesRCP/data/rcp/<cis>.html.gz``: the sibling justelesRCP repository's live
  re-scrape of every ANSM RCP (read only). Dated by its scrape manifest's
  ``last_fetch`` (``data/.scrape-manifest.json``, status ``ok``) when it has one, else
  the file's mtime, the same rule justelesRCP itself uses for its "checked on" date. A
  zero-byte file or a manifest status ``empty`` means "scraped, no RCP" and is skipped.
  Its frozen 2022 ``CIS_RCP.csv`` is never read (it would fail freshness).
* ``../justelesRCP/data/eu/<cis>.html.gz``: only for a drug no ANSM text covers (its
  products all centrally authorised: Briviact, Brintellix, Xeplion), EMA's French SmPC as justelesRCP
  scraped it, dated by ``data/.scrape-ema-manifest.json``'s ``last_fetch`` (else the
  page's ``data-ema-fetched``) and cited at its EMA PDF rather than the ANSM page.

A drug with no CIS product at all (EU-authorised, not marketed in France: Intuniv,
Reagila, Latuda) falls back to its EU centralised authorisation found BY NAME in EMA's
published EPAR tables (``fetch_ema_epar.py``, :func:`epar_copy`): justelesRCP's
converted SmPC when it holds that PDF, else the French (else English) SmPC downloaded
from EMA once and converted with justelesRCP's ``src/ema_pdf.py`` (needs ``pymupdf``).
Its page is keyed by the EMA product number (``EMEA-H-C-003759``), its header names the
EPAR, and the chosen EPAR (product, holder, number, status, dates) is recorded in the
cache under ``ema``.

Which product: the drug's princeps (its brands' CIS from ``bdpm_labels.json``, the
#16 join) first, then the #16 chosen product; the first that has an RCP with a 4.4
section wins. The cited page is the official online one
(``/medicament/<cis>/extrait``, or the EMA PDF), whatever local copy it was read from; the header's
``copied_from`` says which, and ``date_source`` how its date was read.

Writes ``data_sources/bdpm/pages_rcp4/<cis>.md`` (header, then each section as a
``## `` heading, its sub-headings as ``### ``, list items as ``- `` lines, one paragraph
per line) and ``tools/generated_cache/bdpm_rcp_labels.json`` (drug id -> chosen
product, its ``page`` the CIS or the EMA product number), which ``fetch_workup.py`` reads.

Usage (repo root)::

    uv run --with pymupdf python tools/fetch/fetch_bdpm_rcp.py   # pymupdf: a new SmPC
    python tools/fetch/fetch_bdpm_rcp.py --offline                 # stored SmPCs only
    uv run --with pymupdf python tools/fetch/fetch_bdpm_rcp.py --refresh-ema
    python tools/fetch/fetch_bdpm_rcp.py --only lithium,clozapine
    python tools/fetch/fetch_bdpm_rcp.py --justelesrcp /path/to/justelesRCP

Stdlib only (bar that PDF converter); author-side (``data_sources/`` is gitignored). Built with the help of
Claude Code.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE))
import drugs_io  # noqa: E402
from io_atomic import atomic_write_json  # noqa: E402
from lib.corpora import bdpm  # noqa: E402 (section_body, html_lines, the product join, RCP_URL)
import fetch_ema_epar  # noqa: E402 (the EPAR found by name, for a drug with no CIS)

PAGES_DIR = bdpm.BASE_DIR / "pages_rcp4"
CACHE_PATH = ROOT / "tools" / "generated_cache" / "bdpm_rcp_labels.json"
JUSTELESRCP = ROOT.parent / "justelesRCP"

# Drug -> the molecules a combination may pair it with and still count as its RCP
# (folded ``bdpm.molecule_key`` names). Levodopa is sold in France only with a
# decarboxylase inhibitor, and Sinemet's / Modopar's 4.3 / 4.4 asks concern the
# levodopa; the partners themselves get no page (no label speaks for them alone).
COMBO_PARTNERS = {"levodopa": ("CARBIDOPA", "BENSERAZIDE")}

# The sections read, in page order: (number, anchor name the RCP HTML carries).
SECTIONS = (("4.2", "RcpPosoAdmin"), ("4.3", "RcpContreindications"),
            ("4.4", "RcpMisesEnGarde"))
SECTION_TITLES = {"4.2": "4.2. Posologie et mode d'administration",
                  "4.3": "4.3. Contre-indications",
                  "4.4": "4.4. Mises en garde spéciales et précautions d'emploi"}
SECTION_TITLES_EN = {"4.2": "4.2. Posology and method of administration",
                     "4.3": "4.3. Contraindications",
                     "4.4": "4.4. Special warnings and precautions for use"}

_HEAD_MARK, _ITEM_MARK = "\x01", "\x02"
_SUBHEAD_P = re.compile(r"<p[^>]*class=\"?AmmAnnexeTitre[3-9]\"?[^>]*>", re.I)
_ITEM_P = re.compile(r"<p[^>]*class=\"?AmmListePuces\d\"?[^>]*>|<li\b[^>]*>", re.I)


def section_lines(body: str) -> list[str]:
    """One RCP section's HTML as Markdown lines: ``### `` sub-headings, ``- `` items.

    >>> section_lines('<p class="AmmAnnexeTitre3">Avant</p><p class="AmmListePuces1">'
    ...               '· ECG</p><p class="AmmCorpsTexte">Texte.</p>')
    ['### Avant', '- ECG', 'Texte.']
    """
    body = _SUBHEAD_P.sub(lambda m: m.group(0) + _HEAD_MARK, body)
    body = _ITEM_P.sub(lambda m: m.group(0) + _ITEM_MARK, body)
    out = []
    for line in bdpm.html_lines(body):
        mark = line[:1] if line[:1] in (_HEAD_MARK, _ITEM_MARK) else ""
        rest = line.replace(_HEAD_MARK, "").replace(_ITEM_MARK, "")
        if mark:
            rest = rest.lstrip("·•▪- ").strip()
        if len(rest) <= 1:
            continue
        out.append("### " + rest if mark == _HEAD_MARK
                   else "- " + rest if mark == _ITEM_MARK else rest)
    return out


def rcp_sections(page_html: str) -> dict[str, list[str]]:
    """``{"4.2": lines, "4.3": lines, "4.4": lines}`` for the sections the page has."""
    out = {}
    for number, anchor in SECTIONS:
        body = bdpm.section_body(page_html, number, anchor)
        if body is not None:
            lines = section_lines(body)
            if lines:
                out[number] = lines
    return out


# ---------------------------------------------------------------------------- copies

def _mtime_date(path: Path) -> str:
    return dt.datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()


def load_manifest(repo: Path, name: str = ".scrape-manifest.json") -> dict:
    """A justelesRCP scrape manifest: the ANSM one, or ``.scrape-ema-manifest.json``."""
    path = repo / "data" / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _scraped(repo: Path, folder: str, cis: str) -> tuple[str, Path, str] | None:
    """justelesRCP's copy of ``cis`` under ``data/<folder>/`` (gzipped or not) as
    ``(file name, path, html)``, or None when it has none (or a zero-byte one)."""
    for name in (f"{cis}.html.gz", f"{cis}.html"):
        path = repo / "data" / folder / name
        if not path.exists() or not path.stat().st_size:
            continue
        raw = path.read_bytes()
        text = (gzip.decompress(raw) if name.endswith(".gz") else raw).decode(
            "utf-8", errors="replace")
        return name, path, text
    return None


def _manifest_date(entry: dict, how: str) -> tuple[str, str] | None:
    """A scrape manifest entry's ``(last_fetch day, how)`` when it fetched ok, else None."""
    if entry.get("status") == "ok" and entry.get("last_fetch"):
        return entry["last_fetch"][:10], how
    return None


def copies(cis: str, repo: Path, manifest: dict) -> list[dict]:
    """Every local RCP copy of product ``cis``: ``{html, fetched, date_source,
    copied_from}``. A copy known to hold no RCP (zero bytes, manifest ``empty``) is
    not one."""
    out = []
    local = bdpm.RAW_DIR / f"{cis}.html"
    if local.exists() and local.stat().st_size:
        out.append({"html": local.read_text(encoding="utf-8", errors="replace"),
                    "fetched": _mtime_date(local), "date_source": "file mtime",
                    "copied_from": f"neurarium data_sources/bdpm/raw/{cis}.html"})
    entry = manifest.get(cis) or {}
    found = None if entry.get("status") == "empty" else _scraped(repo, "rcp", cis)
    if found:
        name, path, text = found
        fetched, how = (_manifest_date(entry, "justelesRCP scrape manifest last_fetch")
                        or (_mtime_date(path), "file mtime"))
        out.append({"html": text, "fetched": fetched, "date_source": how,
                    "copied_from": f"justelesRCP data/rcp/{name}"})
    return out


_EMA_ATTR = re.compile(r'data-ema-(fetched|pdf)="([^"]+)"')


def ema_copies(cis: str, repo: Path, ema: dict) -> list[dict]:
    """A centrally authorised product's RCP: EMA's French SmPC, which justelesRCP
    stores under ``data/eu/<cis>.html.gz`` (ANSM publishes no text of its own for
    it). Dated by the EMA scrape manifest's ``last_fetch``, else the page's own
    ``data-ema-fetched``; cited at the EMA PDF it was read from."""
    found = _scraped(repo, "eu", cis)
    if not found:
        return []
    name, path, text = found
    attrs = dict(_EMA_ATTR.findall(text[:4000]))
    entry = ema.get(cis) or {}
    fetched, how = (_manifest_date(entry, "justelesRCP EMA scrape manifest last_fetch")
                    or ((attrs["fetched"][:10], "data-ema-fetched") if attrs.get("fetched")
                        else (_mtime_date(path), "file mtime")))
    copy = {"html": text, "fetched": fetched, "date_source": how,
            "copied_from": f"justelesRCP data/eu/{name}"}
    if entry.get("ema_pdf") or attrs.get("pdf"):
        copy["source"] = entry.get("ema_pdf") or attrs["pdf"]
    copy["licence"] = fetch_ema_epar.LICENCE
    return [copy]


def freshest(found: list[dict]) -> dict | None:
    """The most recently fetched copy that has a section 4.4 (ties: first listed)."""
    best = None
    for c in found:
        c["sections"] = rcp_sections(c["html"])
        if "4.4" in c["sections"] and (best is None or c["fetched"] > best["fetched"]):
            best = c
    return best


def candidates(entry: dict, products: list[dict], keys: set[str]) -> list[str]:
    """CIS to try for one drug: its princeps brands (the #16 ``entry``), the #16
    chosen product, then every other marketed single-active product in #16's own
    order (brand-name and plain oral first), then the drug's modified-release ones:
    4.3 / 4.4 are about the molecule, so any of its products can answer."""
    out = [b["cis"] for b in entry.get("brands") or [] if b.get("cis")]
    if entry.get("cis"):
        out.append(entry["cis"])
    out += [p["cis"] for p, _ in bdpm.rank(products, keys)]
    out += sorted(p["cis"] for p in products
                  if p["marketed"] and "active" in p["status"].lower())
    return list(dict.fromkeys(out))


def page_text(product: dict, cis: str, copy: dict) -> str:
    """The stored quote-gate page: provenance header, then each section. A copy that
    is not a CIS product (an EPAR found by name) brings its own ``ids`` header lines."""
    head = [f"# {product.get('denomination') or cis}", *(copy.get("ids") or [f"cis: {cis}"]),
            f"source: {copy.get('source') or bdpm.RCP_URL.format(cis=cis)}",
            f"fetched: {copy['fetched']}", f"date_source: {copy['date_source']}",
            f"copied_from: {copy['copied_from']}",
            f"licence: {copy.get('licence') or 'Licence Ouverte / Open Licence (Etalab)'}", ""]
    titles = SECTION_TITLES_EN if copy.get("language") == "en" else SECTION_TITLES
    body = []
    for number, _ in SECTIONS:
        if number in copy["sections"]:
            body += [f"## {titles[number]}", *copy["sections"][number], ""]
    return "\n".join(head + body)


def epar_copy(drug: dict, keys: set[str], epar: "fetch_ema_epar.Epar", repo: Path,
              ema: dict, refresh: bool) -> tuple[str, dict, dict] | None:
    """``(page, product, copy)`` for a drug no CIS product covers, from its EU
    centralised authorisation found by name (``fetch_ema_epar``): justelesRCP's
    converted copy when it holds that very PDF and reads a 4.4 out of it (page = its
    CIS), else the SmPC downloaded from EMA (page = the EMA product number). None
    without a 4.4."""
    found = epar.lookup(drug, keys)
    if not found:
        return None
    rec, doc, url, lang = found
    info = fetch_ema_epar.describe(rec, doc, url, lang)
    cis = epar.by_pdf.get(url)
    best = freshest(ema_copies(cis, repo, ema)) if cis else None
    page = cis
    if not best:
        cis, page = None, fetch_ema_epar.page_id(rec["ema_product_number"])
        copy = epar.smpc(page, url, refresh)
        best = freshest([copy]) if copy else None
    if not best:
        return None
    best.update(source=url, licence=fetch_ema_epar.LICENCE, language=lang, ema=info)
    if not cis:
        best["ids"] = [f"ema_product: {info['number']}", f"epar: {info['epar']}",
                       f"holder: {info['holder']}", f"language: {lang}"]
    return page, {"denomination": f"{info['product']} ({info['number']})"}, best


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated drug ids")
    ap.add_argument("--justelesrcp", type=Path, default=JUSTELESRCP,
                    help="the justelesRCP checkout (default: a sibling of this repo)")
    ap.add_argument("--refresh-ema", action="store_true",
                    help="re-download EMA's EPAR tables and every SmPC found by name")
    ap.add_argument("--offline", action="store_true",
                    help="never download an SmPC; use only the ones already stored")
    args = ap.parse_args()
    only = {d.strip() for d in args.only.split(",")} if args.only else None
    labels = json.loads((ROOT / "tools" / "generated_cache" / "bdpm_labels.json")
                        .read_text(encoding="utf-8"))
    products = bdpm.load_products(bdpm.read_table(
        bdpm.BASE_DIR / bdpm.PRODUCTS_FILE))
    compo = bdpm.load_compo(bdpm.read_table(
        bdpm.BASE_DIR / bdpm.COMPO_FILE))
    titles = bdpm.fr_titles()
    manifest = load_manifest(args.justelesrcp)
    ema = load_manifest(args.justelesrcp, ".scrape-ema-manifest.json")
    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
    epar = fetch_ema_epar.Epar(args.justelesrcp, ema, args.refresh_ema, args.offline)
    by_name = []
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    missing = []
    for drug in drugs_io.load_drugs():
        did = drug["id"]
        if (only and did not in only) or drugs_io.is_combination(drug):
            continue  # a combination's RCP is not this drug's
        keys = bdpm.drug_keys(drug, titles)
        found = bdpm.products_for(drug, keys, products, compo,
                                        COMBO_PARTNERS.get(did, ()))
        entry = labels.get(did, {})
        chosen = None
        # An ANSM text first; EMA's SmPC only for a drug no national RCP covers.
        for read in (lambda c: copies(c, args.justelesrcp, manifest),
                     lambda c: ema_copies(c, args.justelesrcp, ema)):
            for cis in candidates(entry, found, keys):
                best = freshest(read(cis))
                if best:
                    chosen = (cis, best)
                    break
            if chosen:
                break
        if chosen:
            cis, best = chosen
            product = products.get(cis, {})
        else:   # no CIS product at all: the EU authorisation, found by name
            got = epar_copy(drug, keys, epar, args.justelesrcp, ema, args.refresh_ema)
            if not got:
                cache.pop(did, None)
                missing.append(did)
                continue
            cis, product, best = got
            by_name.append(f"{did} ({best['ema']['product']}, {best['ema']['language']})")
        (PAGES_DIR / f"{cis}.md").write_text(page_text(product, cis, best), encoding="utf-8")
        cache[did] = {"page": cis, "denomination": product.get("denomination"),
                      "fetched": best["fetched"], "date_source": best["date_source"],
                      "sections": sorted(best["sections"])}
        if "ids" not in best:
            cache[did]["cis"] = cis
        if best.get("ema"):
            cache[did]["ema"] = best["ema"]
    cache = dict(sorted(cache.items()))
    atomic_write_json(CACHE_PATH, cache, indent=1, sort_keys=True)
    print(f"[ok] {len(cache)} drug(s) with an RCP 4.x page; {len(missing)} without: "
          f"{', '.join(missing)}")
    print(f"[ok] {len(by_name)} through an EPAR found by name: {', '.join(by_name)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
