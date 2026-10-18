#!/usr/bin/env python
"""Unit tests for corpus #24's EPAR-by-name fallback (``tools/fetch/fetch_ema_epar.py``,
driven by ``fetch_bdpm_rcp.epar_copy``): the name matcher (exact substance, salt words
stripped, chirality guard, non-authorised and veterinary EPARs skipped, combinations
refused, ranking), the SmPC url pick, the bare-paragraph heading reader, and the page
built from a small converted-SmPC fixture.

Stdlib ``unittest`` only, hand-built inputs in a temporary directory, so it runs on a
clone lacking the gitignored ``data_sources/``::

    python -m unittest discover -t tools/tests -s tools/tests -p test_ema_epar.py

Built with the help of Claude Code.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))
from lib.corpora import bdpm  # noqa: E402
import fetch_bdpm_rcp as R  # noqa: E402
import fetch_ema_epar as E  # noqa: E402
import fetch_workup as FW  # noqa: E402


def epar(name, substance, status="Authorised", category="Human", generic="No",
         date="01/01/2015", number=None):
    return {"category": category, "name_of_medicine": name, "active_substance": substance,
            "medicine_status": status, "generic": generic,
            "marketing_authorisation_date": date,
            "ema_product_number": number or f"EMEA/H/C/{abs(hash(name)) % 10**6:06d}",
            "marketing_authorisation_developer_applicant_holder": f"{name} Holder",
            "medicine_url": f"https://www.ema.europa.eu/en/medicines/human/EPAR/{name.lower()}"}


def drug(did, name, brands=()):
    return {"id": did, "name": name, "brands": [{"name": b} for b in brands]}


def matches(d, medicines):
    return [r["name_of_medicine"] for r in
            E.epar_matches(d, bdpm.drug_keys(d, {}), medicines)]


class MatcherTest(unittest.TestCase):
    def test_exact_substance_with_salt_words_stripped(self):
        meds = [epar("Intuniv", "guanfacine hydrochloride"),
                epar("Xadago", "safinamide methanesulfonate"),
                epar("Other", "guanfacine extended")]   # an extra word is not the molecule
        self.assertEqual(matches(drug("guanfacine", "Guanfacine"), meds), ["Intuniv"])
        self.assertEqual(matches(drug("safinamide", "Safinamide"), meds), ["Xadago"])

    def test_withdrawn_refused_and_veterinary_epars_are_skipped(self):
        meds = [epar("Acomplia", "rimonabant", status="Withdrawn"),
                epar("Zimulti", "rimonabant", status="Refused"),
                epar("Vetonly", "rimonabant", category="Veterinary")]
        self.assertEqual(matches(drug("rimonabant", "Rimonabant"), meds), [])

    def test_combination_never_matches_a_single_drug(self):
        meds = [epar("Mysimba", "bupropion hydrochloride;naltrexone hydrochloride"),
                epar("Combo", "levodopa / carbidopa"), epar("Plus", "a + naltrexone")]
        self.assertEqual(matches(drug("naltrexone", "Naltrexone"), meds), [])
        self.assertEqual(E.substances("levodopa / carbidopa"),
                         [("LEVODOPA", None), ("CARBIDOPA", None)])

    def test_enantiomer_never_meets_its_racemate(self):
        meds = [epar("Racemic", "methylphenidate hydrochloride"),
                epar("Single", "dexmethylphenidate hydrochloride")]
        d_only = drug("methylphenidate_d", "Methylphenidate (D)")
        racemate = drug("methylphenidate_dl", "Methylphenidate (D,L)")
        self.assertEqual(matches(d_only, meds), ["Single"])
        self.assertEqual(matches(racemate, meds), ["Racemic"])
        # A stereo-tagged substance is let through only by chirality.tag_allowed.
        self.assertEqual(matches(drug("nicotine", "Nicotine"), [epar("N", "(+)-nicotine")]), [])
        self.assertEqual(matches(drug("nicotine", "Nicotine"), [epar("N", "(-)-nicotine")]), ["N"])

    def test_ranking_known_brand_then_originator_then_oldest(self):
        meds = [epar("Paxneury", "guanfacine hydrochloride", generic="Yes", date="26/02/2025"),
                epar("Late", "guanfacine hydrochloride", date="01/01/2020"),
                epar("Intuniv", "guanfacine hydrochloride", date="17/09/2015")]
        self.assertEqual(matches(drug("guanfacine", "Guanfacine"), meds),
                         ["Intuniv", "Late", "Paxneury"])
        self.assertEqual(matches(drug("guanfacine", "Guanfacine", ["Paxneury"]), meds)[0],
                         "Paxneury")


class SmpcUrlTest(unittest.TestCase):
    def test_french_first_else_english(self):
        en, fr = "https://www.ema.europa.eu/x_en.pdf", "https://www.ema.europa.eu/x_fr.pdf"
        self.assertEqual(E.smpc_url({"document_url": en, "translations": {"fr": fr}}), (fr, "fr"))
        self.assertEqual(E.smpc_url({"document_url": en}), (en, "en"))
        self.assertIsNone(E.smpc_url({}))

    def test_a_url_off_ema_is_never_picked(self):
        """Regression: the url comes from a downloaded table, so only EMA's own host is
        fetched; a planted French url falls back to the English EMA one."""
        doc = {"document_url": "https://www.ema.europa.eu/en/x_en.pdf",
               "translations": {"fr": "https://evil.example/x_fr.pdf"}}
        self.assertEqual(E.smpc_url(doc), ("https://www.ema.europa.eu/en/x_en.pdf", "en"))
        self.assertIsNone(E.smpc_url({"document_url": "http://www.ema.europa.eu/x.pdf"}))
        self.assertIsNone(E.smpc_url({"document_url": "https://www.ema.europa.eu.evil/x"}))

    def test_ids_and_dates(self):
        self.assertEqual(E.page_id("EMEA/H/C/003759"), "EMEA-H-C-003759")
        self.assertEqual(E.iso("17/09/2015"), "2015-09-17")
        self.assertEqual(E.iso("2026-10-13T16:10:00Z"), "2026-10-13")


# A converted SmPC whose PDF converter missed the 4.x headings' bold: they are plain
# paragraphs, and a body cross-reference "(voir rubriques 4.4 et 5.3)" is not one.
PLAIN = ('<div id="textDocument"><h2 class="AmmAnnexeTitre1">4. DONNÉES CLINIQUES</h2>'
         '<p>4.2. Posologie et mode d’administration</p><p>Une dose par jour.</p>'
         '<p>4.3. Contre-indications</p><p>Hypersensibilité (voir rubriques 4.4 et 5.3).</p>'
         '<p>4.4. Mises en garde spéciales et précautions d’emploi</p>'
         '<p>La pression artérielle doit être mesurée avant le traitement.</p>'
         '<p>4.5. Interactions avec d’autres médicaments</p><p>Hors sujet.</p>'
         '<h2 class="AmmAnnexeTitre1">5. PROPRIÉTÉS</h2></div>')


class PageBuilderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        raw = Path(self.tmp.name)
        self.saved = E.RAW_DIR
        E.RAW_DIR = raw
        (raw / "EMEA-H-C-003759.html").write_text(PLAIN, encoding="utf-8")
        (raw / "EMEA-H-C-003759.json").write_text(json.dumps(
            {"source": "https://www.ema.europa.eu/fr/x_fr.pdf", "fetched": "2026-10-16"}))
        rec = epar("Intuniv", "guanfacine hydrochloride", number="EMEA/H/C/003759")
        doc = {"type": "product-information", "ema_product_number": "EMEA/H/C/003759",
               "last_updated_date": "2026-10-13T16:10:00Z",
               "translations": {"fr": "https://www.ema.europa.eu/fr/x_fr.pdf"}}
        self.epar = object.__new__(E.Epar)
        self.epar.medicines, self.epar.docs = [rec], E.product_information([doc])
        self.epar.by_pdf, self.epar.offline, self.epar.justelesrcp = {}, True, raw

    def tearDown(self):
        E.RAW_DIR = self.saved
        self.tmp.cleanup()

    def test_plain_paragraph_headings_bound_each_section(self):
        secs = R.rcp_sections(PLAIN)
        self.assertEqual(secs["4.3"], ["Hypersensibilité (voir rubriques 4.4 et 5.3)."])
        self.assertEqual(secs["4.4"], ["La pression artérielle doit être mesurée avant le traitement."])
        self.assertEqual(secs["4.2"], ["Une dose par jour."])

    def test_page_is_the_epar_cited_at_its_ema_pdf(self):
        d = drug("guanfacine", "Guanfacine")
        page, product, copy = R.epar_copy(d, bdpm.drug_keys(d, {}), self.epar,
                                          Path(self.tmp.name), {}, False)
        self.assertEqual(page, "EMEA-H-C-003759")
        self.assertEqual(copy["ema"]["holder"], "Intuniv Holder")
        self.assertEqual(copy["ema"]["pi_updated"], "2026-10-13")
        text = R.page_text(product, page, copy)
        self.assertTrue(text.startswith("# Intuniv (EMEA/H/C/003759)\nema_product: EMEA/H/C/003759"))
        self.assertNotIn("cis:", text)
        self.assertIn("source: https://www.ema.europa.eu/fr/x_fr.pdf", text)
        self.assertIn("fetched: 2026-10-16", text)
        self.assertIn("licence: European Medicines Agency", text)
        line = [ln for ln in FW.page_lines(text) if ln["line"].startswith("La pression")][0]
        self.assertEqual(line["section"], "4.4")

    def test_no_epar_no_page(self):
        d = drug("atomoxetine", "Atomoxetine", ["Strattera"])
        self.assertIsNone(R.epar_copy(d, bdpm.drug_keys(d, {}), self.epar,
                                      Path(self.tmp.name), {}, False))


class ConverterIsolationTest(unittest.TestCase):
    """Regression: the sibling converter ran in-process; it now runs in a ``python -I``
    child, so neither its directory nor ours is on the child's import path."""

    def test_converter_runs_in_an_isolated_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp, "src")
            src.mkdir()
            # A planted module next to the converter: an un-isolated import would load it.
            (src / "planted.py").write_text("LOADED = True\n", encoding="utf-8")
            (src / "ema_pdf.py").write_text(
                "import sys\n"
                "def convert(pdf):\n"
                "    try:\n"
                "        import planted  # noqa: F401\n"
                "        shadowed = True\n"
                "    except ImportError:\n"
                "        shadowed = False\n"
                "    return {'html': str(sys.flags.isolated), 'date': str(shadowed),\n"
                "            'n': len(pdf)}\n", encoding="utf-8")
            epar = E.Epar.__new__(E.Epar)
            epar.justelesrcp = Path(tmp)
            self.assertEqual(epar.convert(b"%PDF-1.4"), {"html": "1", "date": "False", "n": 8})

    def test_a_failing_converter_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "src").mkdir()
            Path(tmp, "src", "ema_pdf.py").write_text(
                "def convert(pdf):\n    raise ValueError('too many pages')\n", encoding="utf-8")
            epar = E.Epar.__new__(E.Epar)
            epar.justelesrcp = Path(tmp)
            with self.assertRaisesRegex(RuntimeError, "too many pages"):
                epar.convert(b"%PDF")


if __name__ == "__main__":
    unittest.main()
