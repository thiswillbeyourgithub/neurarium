#!/usr/bin/env python
"""Find a drug's EU centralised authorisation BY NAME and read its SmPC: corpus #24's
EMA fallback for a drug with no French CIS product at all (guanfacine = Intuniv).

``fetch_bdpm_rcp.ema_copies`` already reads EMA's French SmPC, but only through a CIS:
justelesRCP stores it under ``data/eu/<cis>.html.gz``, which exists only when the
centrally authorised product is also listed in the French database. A drug authorised
in the EU but not marketed in France (Intuniv, Reagila, Latuda) has no CIS, so this
module joins it on EMA's own published tables instead:

* ``medicines-output-medicines_json-report_en.json`` (EMA's "Medicines output" report,
  one record per EPAR: name, ``ema_product_number``, ``active_substance``, status,
  holder, dates, ``medicine_url``);
* ``documents-output-epar_documents_json-report_en.json`` (every EPAR document, the
  ``product-information`` one carrying the SmPC PDF url per language).

Both are downloaded once into ``data_sources/ema/raw/`` (``--refresh-ema`` re-pulls).

Match (:func:`epar_matches`): a **human**, **authorised** EPAR whose active substance
is exactly one molecule (a ``;`` / ``/`` / ``+`` / `` and `` list is a combination and
never matches a single drug) and whose folded molecule, salt words stripped
(``bdpm.molecule_key`` with :data:`EN_SALT_WORDS`), is one of the drug's
own ``bdpm.drug_keys``. A stereo-qualified drug id joins only through
``bdpm.FR_ALIASES`` (so dexmethylphenidate never meets methylphenidate) and a
stereo-tagged substance is let through only by ``chirality.tag_allowed``. Several
matches (the originator and its generics) are ranked: a brand the drug already lists
first, then the non-generic, then the oldest authorisation.

The SmPC: the French product-information PDF (English when EMA has no French one),
preferring a copy justelesRCP already converted (its EMA manifest maps PDF url -> CIS),
else downloaded politely (EMA's own host only, :func:`is_ema_url`) and converted with
justelesRCP's own ``src/ema_pdf.py`` in an isolated ``python -I`` child (needs
``pymupdf``: run under ``uv run --with pymupdf``), the converted HTML kept under
``data_sources/ema/raw/<page>.html`` with a ``.json`` sidecar dating it, so a re-run is
offline. ``<page>`` is the EMA product number made filename-safe
(``EMEA/H/C/003759`` -> ``EMEA-H-C-003759``).

Import-only: ``fetch_bdpm_rcp.py`` drives it. Stdlib only apart from that converter.
Built with the help of Claude Code.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE))
import chirality  # noqa: E402
import polite_http  # noqa: E402 (the one polite GET)
import salt_words  # noqa: E402 (the shared English salt words)
from lib.corpora import bdpm  # noqa: E402 (fold, molecule_key)

EMA = "https://www.ema.europa.eu/en/documents/report/"
MEDICINES_URL = EMA + "medicines-output-medicines_json-report_en.json"
DOCUMENTS_URL = EMA + "documents-output-epar_documents_json-report_en.json"
RAW_DIR = ROOT / "data_sources" / "ema" / "raw"
MEDICINES_FILE = RAW_DIR / "medicines.json"
DOCUMENTS_FILE = RAW_DIR / "epar_documents.json"
LICENCE = "European Medicines Agency, reproduction authorised, source acknowledged"

# EMA's ``active_substance`` wraps a molecule in English salt words ("guanfacine
# hydrochloride"): the shared list, see ``tools/salt_words.py``.
EN_SALT_WORDS = salt_words.EN_SALT_WORDS
COMBO_SPLIT = re.compile(r"\s*(?:;|/|\+|\band\b)\s*", re.I)


def page_id(number: str) -> str:
    """An EMA product number as a page id: ``EMEA/H/C/003759`` -> ``EMEA-H-C-003759``."""
    return number.strip().replace("/", "-")


def iso(date: str) -> str:
    """EMA's ``dd/mm/yyyy`` (or an ISO timestamp) as ``yyyy-mm-dd``; "" when empty."""
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", (date or "").strip())
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else (date or "")[:10]


def substances(active: str) -> list[tuple[str, str | None]]:
    """``active_substance`` as ``[(molecule, stereo tag)]``, one per listed substance.

    >>> substances("guanfacine hydrochloride")
    [('GUANFACINE', None)]
    >>> substances("bupropion hydrochloride;naltrexone hydrochloride")
    [('BUPROPION', None), ('NALTREXONE', None)]
    """
    parts = [p for p in COMBO_SPLIT.split(active or "") if p.strip()]
    return [bdpm.molecule_key(p, EN_SALT_WORDS) for p in parts]


def epar_matches(drug: dict, keys: set[str], medicines: list[dict]) -> list[dict]:
    """The human, authorised, single-substance EPARs of ``drug`` (folded ``keys``,
    ``bdpm.drug_keys``), best first (see the module docstring)."""
    brands = {bdpm.fold(b.get("name") or "") for b in drug.get("brands") or []}
    out = []
    for rec in medicines:
        if rec.get("category") != "Human" or rec.get("medicine_status") != "Authorised":
            continue
        subs = substances(rec.get("active_substance") or "")
        if len(subs) != 1:
            continue  # a combination's label is not this drug's
        molecule, tag = subs[0]
        if molecule in keys and chirality.tag_allowed(tag, drug["id"]):
            out.append(rec)
    def rank(rec):
        name = bdpm.fold(rec.get("name_of_medicine") or "")
        named = name in brands or name.split(" ")[0] in brands
        return (not named, rec.get("generic") == "Yes",
                iso(rec.get("marketing_authorisation_date") or "") or "9999",
                rec.get("name_of_medicine") or "")
    return sorted(out, key=rank)


def product_information(documents: list[dict]) -> dict[str, dict]:
    """EMA product number -> its ``product-information`` document record."""
    out = {}
    for doc in documents:
        if doc.get("type") == "product-information" and doc.get("ema_product_number"):
            out.setdefault(doc["ema_product_number"], doc)
    return out


# The only host a url read off EMA's downloaded tables may point at: the tables are
# downloaded data, so a url in them is never fetched unless it is EMA's own.
EMA_ORIGIN = "https://www.ema.europa.eu/"


def is_ema_url(url: object) -> bool:
    """True for an ``https://www.ema.europa.eu/`` url, the one host this module fetches."""
    return isinstance(url, str) and url.startswith(EMA_ORIGIN)


def smpc_url(doc: dict) -> tuple[str, str] | None:
    """``(pdf url, language)``: the French PDF, else the English one, else None. A url
    off EMA's own host is skipped, never fetched (:func:`is_ema_url`)."""
    for url, lang in (((doc.get("translations") or {}).get("fr"), "fr"),
                      (doc.get("document_url"), "en")):
        if is_ema_url(url):
            return url, lang
    return None


def describe(rec: dict, doc: dict, url: str, lang: str) -> dict:
    """The reviewable record of the chosen EPAR, as the cache stores it."""
    return {"product": rec.get("name_of_medicine"), "number": rec.get("ema_product_number"),
            "holder": rec.get("marketing_authorisation_developer_applicant_holder"),
            "status": rec.get("medicine_status"), "generic": rec.get("generic") == "Yes",
            "authorised": iso(rec.get("marketing_authorisation_date") or ""),
            "pi_updated": iso(doc.get("last_updated_date") or ""),
            "epar": rec.get("medicine_url"), "pdf": url, "language": lang}


# ---------------------------------------------------------------------------- network

def _load_table(path: Path, url: str, refresh: bool) -> list[dict]:
    if refresh or not path.exists():
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        print(f"  [ema] downloading {url}")
        raw = polite_http.fetch_or_none(url, binary=True)
        if raw is None:
            raise SystemExit(f"[error] could not download {url}")
        path.write_bytes(raw)
    return json.loads(path.read_text(encoding="utf-8"))["data"]


# Loads justelesRCP's converter by path and runs it on stdin: the body of the isolated
# child :meth:`Epar.convert` spawns (argv[1] = the converter's path).
_CONVERT_CHILD = (
    "import importlib.util, json, sys\n"
    "spec = importlib.util.spec_from_file_location('justelesrcp_ema_pdf', sys.argv[1])\n"
    "mod = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(mod)\n"
    "json.dump(mod.convert(sys.stdin.buffer.read()), sys.stdout)\n"
)


class Epar:
    """EMA's two tables plus the SmPC store; one instance per fetcher run."""

    def __init__(self, justelesrcp: Path, ema_manifest: dict, refresh: bool = False,
                 offline: bool = False):
        self.medicines = _load_table(MEDICINES_FILE, MEDICINES_URL, refresh)
        self.docs = product_information(_load_table(DOCUMENTS_FILE, DOCUMENTS_URL, refresh))
        self.justelesrcp, self.offline = justelesrcp, offline
        # A PDF justelesRCP already converted, keyed by its url (it names the CIS).
        self.by_pdf = {e["ema_pdf"]: cis for cis, e in ema_manifest.items()
                       if isinstance(e, dict) and e.get("ema_pdf")}

    def lookup(self, drug: dict, keys: set[str]) -> tuple[dict, dict, str, str] | None:
        """``(epar record, its PI document, pdf url, language)`` for the best EPAR
        that has a product-information PDF, else None."""
        for rec in epar_matches(drug, keys, self.medicines):
            doc = self.docs.get(rec.get("ema_product_number"))
            found = smpc_url(doc) if doc else None
            if found:
                return rec, doc, *found
        return None

    def convert(self, pdf: bytes) -> dict:
        """justelesRCP's ``src/ema_pdf.convert`` over ``pdf`` (needs pymupdf: ``uv run
        --with pymupdf``), run in a ``python -I`` child: the sibling checkout is not ours,
        so it never shares this process, and isolation keeps its directory (or ours) off
        the child's import path. The PDF goes in on stdin, the ``{html, date}`` dict comes
        back as JSON; a failing converter raises with its stderr tail."""
        path = self.justelesrcp / "src" / "ema_pdf.py"
        proc = subprocess.run([sys.executable, "-I", "-c", _CONVERT_CHILD, str(path)],
                              input=pdf, capture_output=True, timeout=600, check=False)
        if proc.returncode:
            raise RuntimeError(f"{path} failed (exit {proc.returncode}): "
                               f"{proc.stderr.decode('utf-8', 'replace')[-2000:]}")
        return json.loads(proc.stdout)

    def smpc(self, page: str, url: str, refresh: bool = False) -> dict | None:
        """The converted SmPC ``{html, fetched, date_source, copied_from}`` for ``page``,
        read from ``data_sources/ema/raw/<page>.html`` or downloaded + converted."""
        html_path, meta_path = RAW_DIR / f"{page}.html", RAW_DIR / f"{page}.json"
        if not refresh and html_path.exists() and meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("source") == url:
                return {"html": html_path.read_text(encoding="utf-8"),
                        "fetched": meta["fetched"], "date_source": "download date",
                        "copied_from": f"neurarium data_sources/ema/raw/{page}.html"}
        if self.offline:
            return None
        if not is_ema_url(url):
            raise ValueError(f"refusing to fetch {url!r}: not an {EMA_ORIGIN} url")
        print(f"  [ema] downloading {url}")
        pdf = polite_http.fetch_or_none(url, binary=True)
        if not pdf or not pdf.startswith(b"%PDF"):
            return None
        conv = self.convert(pdf)
        if not conv.get("html"):
            return None
        fetched = dt.date.today().isoformat()
        html_path.write_text(conv["html"], encoding="utf-8")
        meta_path.write_text(json.dumps({"source": url, "fetched": fetched,
                                         "pdf_date": conv.get("date")}, indent=1) + "\n",
                             encoding="utf-8")
        return {"html": conv["html"], "fetched": fetched, "date_source": "download date",
                "copied_from": f"neurarium data_sources/ema/raw/{page}.html"}
