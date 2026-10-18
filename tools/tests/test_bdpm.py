#!/usr/bin/env python
"""Unit tests for the BDPM corpus #16 fetcher join (``tools/fetch/fetch_bdpm.py``) and the
French duration parsing it feeds into ``fetch_tmax``.

Stdlib ``unittest`` only, over hand-built table rows, so it runs on a clone that lacks the
gitignored ``data_sources/bdpm/`` tree::

    python tools/tests/test_bdpm.py

Built with the help of Claude Code.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
import fetch_bdpm as B  # noqa: E402
import fetch_tmax  # noqa: E402


def product(cis, denomination, form="comprimé", route="orale", marketed=True):
    return {"cis": cis, "denomination": denomination, "form": form, "route": route,
            "status": "Autorisation active", "marketed": marketed, "holder": "LAB"}


def sa(name, link="1"):
    return {"name": name, "nature": "SA", "link": link}


class JoinTest(unittest.TestCase):
    def setUp(self):
        self.products = {
            "1": product("1", "SEROPRAM 20 mg, comprimé pelliculé sécable"),
            "2": product("2", "SEROPLEX 10 mg, comprimé pelliculé sécable"),
            "3": product("3", "COMBO 5 mg, comprimé"),
            "4": product("4", "LYSERGIC, granules", form="granules"),
        }
        self.compo = {
            "1": [sa("BROMHYDRATE DE CITALOPRAM"),
                  {"name": "CITALOPRAM BASE", "nature": "FT", "link": "1"}],
            "2": [sa("OXALATE D'ESCITALOPRAM")],
            "3": [sa("CHLORHYDRATE DE CITALOPRAM", "1"), sa("SOMETHING ELSE", "2")],
            "4": [sa("CITALOPRAM POUR PRÉPARATIONS HOMÉOPATHIQUES")],
        }

    def join(self, drug):
        keys = B.drug_keys(drug, {})
        return sorted(p["cis"] for p in B.products_for(drug, keys, self.products, self.compo))

    def test_enantiomer_never_matches_racemate(self):
        """escitalopram's products never join citalopram and vice versa (exact match)."""
        self.assertEqual(self.join({"id": "citalopram", "name": "Citalopram"}), ["1"])
        self.assertEqual(self.join({"id": "escitalopram", "name": "Escitalopram"}), ["2"])

    def test_combination_and_homeopathy_skipped(self):
        """A two-active product (3) and a homeopathic dilution (4) are not the drug."""
        self.assertNotIn("3", self.join({"id": "citalopram", "name": "Citalopram"}))
        self.assertNotIn("4", self.join({"id": "citalopram", "name": "Citalopram"}))

    def test_combination_with_listed_partner_only(self):
        """levodopa + carbidopa joins when the partner is allowed; a third active does not."""
        self.products.update({"5": product("5", "SINEMET 250 mg/25 mg, comprimé"),
                              "6": product("6", "STALEVO, comprimé")})
        self.compo.update({"5": [sa("LÉVODOPA", "1"), sa("CARBIDOPA MONOHYDRATÉE", "2")],
                           "6": [sa("LÉVODOPA", "1"), sa("CARBIDOPA", "2"),
                                 sa("ENTACAPONE", "3")]})
        drug = {"id": "levodopa", "name": "Levodopa"}
        keys = B.drug_keys(drug, {})
        join = lambda partners: sorted(p["cis"] for p in B.products_for(
            drug, keys, self.products, self.compo, partners))
        self.assertEqual(join(()), [])
        self.assertEqual(join(("CARBIDOPA", "BENSERAZIDE")), ["5"])

    def test_benzoate_and_palmitate_are_salts(self):
        """The salt words rizatriptan and paliperidone missed the join on."""
        self.assertEqual(B.molecule_key("BENZOATE DE RIZATRIPTAN")[0], "RIZATRIPTAN")
        self.assertEqual(B.molecule_key("PALMITATE DE PALIPÉRIDONE")[0], "PALIPERIDONE")

    def test_stereo_qualified_name_joins_only_by_alias(self):
        """"Methylphenidate (D)" must not reduce to METHYLPHENIDATE (the racemate)."""
        keys = B.drug_keys({"id": "methylphenidate_d", "name": "Methylphenidate (D)"}, {})
        self.assertNotIn("METHYLPHENIDATE", keys)
        self.assertIn("DEXMETHYLPHENIDATE", keys)

    def test_prodrug_ft_line_ignored(self):
        """lisdexamfetamine's FT line (DEXAMFETAMINE) does not make it dexamfetamine."""
        lines = [sa("DIMÉSILATE DE LISDEXAMFÉTAMINE"),
                 {"name": "DEXAMFÉTAMINE", "nature": "FT", "link": "1"}]
        self.assertFalse(B.matches("amphetamine_d", {"DEXAMFETAMINE"}, lines))

    def test_french_suffix_and_inverted_salt(self):
        keys = B.drug_keys({"id": "vigabatrin", "name": "Vigabatrin"}, {})
        self.assertIn("VIGABATRINE", keys)
        self.assertEqual(B.molecule_key("SODIUM (VALPROATE DE)")[0], "VALPROATE")


class RankTest(unittest.TestCase):
    def test_prolonged_release_never_supplies_the_ir_rcp(self):
        """An LP product (the Seroquel XR gotcha) is never the representative RCP."""
        keys = {"QUETIAPINE"}
        ps = [product("10", "XEROQUEL LP 50 mg, comprimé à libération prolongée",
                      form="comprimé à libération prolongée"),
              product("11", "QUETIAPINE TEVA 25 mg, comprimé pelliculé"),
              product("12", "XEROQUEL 25 mg, comprimé pelliculé")]
        for p in ps:
            p["substances"] = ["FUMARATE DE QUÉTIAPINE"]
        ranked = [p["cis"] for p, _ in B.rank(ps, keys)]
        self.assertEqual(ranked, ["12", "11"])          # brand first, LP absent

    def test_only_lp_marketed_gives_nothing(self):
        p = product("20", "ZYBAN L.P. 150 mg, comprimé à libération prolongée",
                    form="comprimé à libération prolongée")
        self.assertEqual(B.rank([p], {"BUPROPION"}), [])

    def test_local_route_never_a_fallback(self):
        p = product("30", "ATROPINE ALCON 0,5 POUR CENT, collyre", form="collyre",
                    route="ophtalmique")
        self.assertEqual(B.rank([p], {"ATROPINE"}), [])


class BrandTest(unittest.TestCase):
    """The generic-exclusion rule of ``brand_of``."""

    def brand(self, denomination, subs=("LOPRAZOLAM",), keys=("LOPRAZOLAM",), route="orale"):
        p = product("1", denomination, route=route)
        p["substances"] = list(subs)
        return B.brand_of(p, set(keys))

    def test_brand(self):
        self.assertEqual(self.brand("HAVLANE, comprimé sécable"), "HAVLANE")
        self.assertEqual(self.brand("DEPAKINE CHRONO 500 mg, comprimé",
                                    ("VALPROATE DE SODIUM",), ("VALPROATE",)), "DEPAKINE")

    def test_inn_named_generic(self):
        self.assertIsNone(self.brand("LOPRAZOLAM TEVA 1 mg, comprimé"))
        self.assertIsNone(self.brand("ACIDE VALPROIQUE ARROW 200 mg, comprimé",
                                     ("ACIDE VALPROÏQUE",), ("ACIDE VALPROIQUE",)))
        self.assertIsNone(self.brand("VALPROATE DE SODIUM MYLAN 500 mg",
                                     ("VALPROATE DE SODIUM",), ("VALPROATE",)))

    def test_range_name_and_lab_and_local_route(self):
        self.assertIsNone(self.brand("GRANIONS DE LITHIUM, solution buvable",
                                     ("GLUCONATE DE LITHIUM",), ("LITHIUM",)))
        self.assertIsNone(self.brand("ZOLPI BIOGARAN 10 mg", ("ZOLPIDEM",), ("ZOLPIDEM",)))
        self.assertIsNone(self.brand("LITHIODERM, gel", ("GLUCONATE DE LITHIUM",),
                                     ("LITHIUM",), route="cutanée"))

    def test_display_casing(self):
        self.assertEqual(B.display_brand("DI-HYDAN"), "Di-Hydan")


class FrenchDurationTest(unittest.TestCase):
    def test_durations(self):
        self.assertEqual(fetch_tmax.durations_in_fr("un Tmax atteint en 1 heure environ"),
                         [{"hours": 1.0}])
        self.assertEqual(fetch_tmax.durations_in_fr("entre 1,5 et 3 heures"),
                         [{"hours": 1.5, "hours_max": 3.0}])
        self.assertEqual(fetch_tmax.durations_in_fr("de 15 à 17 heures"),
                         [{"hours": 15.0, "hours_max": 17.0}])

    def test_hours_and_minutes_and_mixed_units(self):
        self.assertEqual(fetch_tmax.durations_in_fr("environ 1h30 après la prise"),
                         [{"hours": 1.5}])
        self.assertEqual(fetch_tmax.durations_in_fr("30 min à 1 heure 30 plus tard"),
                         [{"hours": 0.5, "hours_max": 1.5}])

    def test_et_is_a_range_only_after_entre(self):
        """"en 2 et 3 heures respectivement" is venlafaxine's 2 h and ODV's 3 h."""
        self.assertEqual(fetch_tmax.durations_in_fr("respectivement en 2 et 3 heures"),
                         [{"hours": 2.0}, {"hours": 3.0}])
        self.assertEqual(fetch_tmax.durations_in_fr("entre 2 et 4 heures"),
                         [{"hours": 2.0, "hours_max": 4.0}])

    def test_bdpm_page_resolves_through_the_registry(self):
        from pipeline.gate import registry_pages
        pages = registry_pages()
        self.assertEqual(pages["bdpm"], ROOT / "data_sources" / "bdpm" / "pages")
        self.assertNotIn("nope", pages)


class BrandApplyTest(unittest.TestCase):
    """``apply_brand_names.apply_bdpm``: code-read brands, gated on the product page."""

    def test_add_skip_and_gate(self):
        import tempfile
        import apply_brand_names as A
        with tempfile.TemporaryDirectory() as tmp:
            pages = Path(tmp)
            (pages / "1.md").write_text("# HAVLANE, comprimé sécable\ncis: 1\n", "utf-8")
            (pages / "2.md").write_text("# THERALENE 5 mg, comprimé\ncis: 2\n", "utf-8")
            (pages / "3.md").write_text("# OTHER, comprimé\ncis: 3\n", "utf-8")
            drugs = [{"id": "loprazolam", "brands": []},
                     {"id": "alimemazine", "brands": [{"name": "Théralène", "region": "fr",
                                                       "sources": []}]}]
            labels = {"loprazolam": {"brands": [
                          {"name": "Havlane", "quote": "HAVLANE", "cis": "1"},
                          {"name": "Ghost", "quote": "GHOST", "cis": "3"}]},
                      "alimemazine": {"brands": [
                          {"name": "Theralene", "quote": "THERALENE", "cis": "2"}]}}
            touched, added, present, misses = A.apply_bdpm(drugs, labels, pages)
        self.assertEqual((touched, added, present, len(misses)), (1, 1, 1, 1))
        self.assertEqual(drugs[0]["brands"], [{
            "name": "Havlane", "region": "fr",
            "sources": [{"corpus": "bdpm", "page": "1", "quote": "HAVLANE",
                         "provenance": "verified", "extraction": "code"}]}])
        self.assertEqual(len(drugs[1]["brands"]), 1)       # accent-folded duplicate

    def test_brand_key_folds_accents_case_and_spaces(self):
        # French Wikipedia writes Stahl's "Risperdal Consta" as "Risperdalconsta" and
        # "Tranxene" as "Tranxène": both once shipped as a second brand node.
        import apply_brand_names as A
        self.assertEqual(A.brand_key("Risperdal Consta"), A.brand_key("Risperdalconsta"))
        self.assertEqual(A.brand_key("Tranxene"), A.brand_key("Tranxène"))
        self.assertNotEqual(A.brand_key("Risperdal"), A.brand_key("Risperdal Consta"))
        seen = {A.brand_key("Risperdal Consta")}
        self.assertFalse(A.add_brand([], seen, "Risperdalconsta", "fr", {}))

    def test_merge_duplicate_brands_keeps_first_and_unions(self):
        import apply_brand_names as A
        stahl = {"corpus": "stahl", "page": 199, "quote": "Tranxene"}
        wiki = {"corpus": "wikipedia_fr", "page": "cloraz_pate", "quote": "Tranxène"}
        other = {"name": "Tranxilium", "region": "eu", "sources": [wiki]}
        drugs = [{"id": "clorazepate", "brands": [
            {"name": "Tranxene", "region": "na", "sources": [stahl]},
            {"name": "Tranxène", "region": "fr", "sources": [wiki]}, other]}]
        self.assertEqual(A.merge_duplicate_brands(drugs),
                         ["clorazepate: 'Tranxene' <- 'Tranxène'"])
        self.assertEqual(drugs[0]["brands"], [
            {"name": "Tranxene", "region": ["na", "fr"], "sources": [stahl, wiki]}, other])
        self.assertEqual(A.merge_duplicate_brands(drugs), [])   # idempotent

    def test_a_brand_region_may_be_a_list(self):
        from data_generators.provenance import _drug_brands
        got = _drug_brands("x", [{"name": "Tranxene", "region": ["na", "fr"]}])
        self.assertEqual(got[0]["region"], ["na", "fr"])
        for bad in (["na", "xx"], [], ["na", "na"], "xx"):
            with self.assertRaises(ValueError):
                _drug_brands("x", [{"name": "Tranxene", "region": bad}])


if __name__ == "__main__":
    unittest.main()
