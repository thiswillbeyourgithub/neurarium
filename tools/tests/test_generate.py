#!/usr/bin/env python
"""Test harness guarding tools/generate_data.py.

Stdlib unittest only (no deps). Runnable directly:

    python tools/tests/test_generate.py

Also pytest-discoverable. Two families of test:

* **Golden**: the byte-identical regeneration of ``public/data/`` lives in
  ``test_generated_artifacts_fresh.py`` (with every other generated artifact).
* **Data-integrity**: read the *emitted* files under ``public/data/`` (never
  import generator internals) so these assertions survive the refactor.
"""

import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "public" / "data"


def _load_jsonl(path):
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


class ReceptorTest(unittest.TestCase):
    # Pinned regression guard (re-verified against the real data 2026-07-16, after
    # the obsolete alpha1c stub was removed: adrenergic 11 -> 10, total 63 -> 62).
    EXPECTED_FAMILIES = {
        "serotonergic": 13,
        "adrenergic": 10,
        "glutamatergic": 10,
        "cholinergic": 8,
        "dopaminergic": 5,
        "histaminergic": 4,
        "gabaergic": 3,
        "opioidergic": 3,
        "melatonergic": 2,
        "cannabinoid": 1,
        "glycinergic": 1,
        "purinergic": 1,
        "sigma": 1,
    }

    @classmethod
    def setUpClass(cls):
        cls.receptors = _load_jsonl(DATA_DIR / "receptors.jsonl")

    def test_count_and_unique_ids(self):
        self.assertEqual(len(self.receptors), 62)
        ids = [r["id"] for r in self.receptors]
        self.assertEqual(len(set(ids)), 62, "receptor ids are not unique")

    def test_family_distribution(self):
        counts = {}
        for r in self.receptors:
            counts[r["family"]] = counts.get(r["family"], 0) + 1
        self.assertEqual(counts, self.EXPECTED_FAMILIES)
        self.assertEqual(sum(counts.values()), 62)


class ReferentialIntegrityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.structures = _load_jsonl(DATA_DIR / "structures.jsonl")
        cls.receptors = _load_jsonl(DATA_DIR / "receptors.jsonl")
        cls.projections = _load_jsonl(DATA_DIR / "projections.jsonl")
        cls.drugs = _load_jsonl(DATA_DIR / "drugs.jsonl")
        cls.struct_ids = {s["id"] for s in cls.structures}
        # A receptor location is a *base* id (no _L/_R hemisphere suffix);
        # accept both the exact id and the base form.
        cls.location_ids = cls.struct_ids | {
            re.sub(r"_[LR]$", "", i) for i in cls.struct_ids
        }

    def _receptor_regions(self, rec):
        if "structureIds" in rec:
            return rec["structureIds"]
        locs = rec.get("locations")
        if isinstance(locs, str):  # "ALL" -> ubiquitous, no region refs
            return []
        return locs or []

    def test_receptor_regions_resolve(self):
        for rec in self.receptors:
            for region in self._receptor_regions(rec):
                self.assertIn(
                    region,
                    self.location_ids,
                    f"receptor {rec['id']} references unknown region {region!r}",
                )

    def test_projection_endpoints_resolve(self):
        for p in self.projections:
            src = p.get("source", p.get("from"))
            tgt = p.get("target", p.get("to"))
            self.assertIn(src, self.struct_ids, f"projection source {src!r} unknown")
            self.assertIn(tgt, self.struct_ids, f"projection target {tgt!r} unknown")

    def test_mirror_expansion_is_bilateral(self):
        """A symmetric pathway is emitted once with ``mirror: true`` (not as two
        rows); flipping ``_R`` <-> ``_L`` on both endpoints must land on real
        structures, and the flip must actually differ from the stored record (else
        the flag would be dead). Mirrors the viewer/check_data expansion."""
        def flip(sid):
            if sid.endswith("_R"):
                return sid[:-2] + "_L"
            if sid.endswith("_L"):
                return sid[:-2] + "_R"
            return sid

        mirrored = [p for p in self.projections if p.get("mirror")]
        self.assertTrue(mirrored, "expected some mirrored (bilateral) projections")
        stored = {(p.get("from"), p.get("to")) for p in self.projections}
        for p in mirrored:
            twin = (flip(p["from"]), flip(p["to"]))
            self.assertNotEqual(
                twin, (p["from"], p["to"]),
                f"mirror:true on a pathway whose flip is a no-op: {p['from']}->{p['to']}",
            )
            self.assertIn(twin[0], self.struct_ids, f"mirrored source {twin[0]!r} unknown")
            self.assertIn(twin[1], self.struct_ids, f"mirrored target {twin[1]!r} unknown")
            self.assertNotIn(
                twin, stored,
                f"pathway {twin} is both stored and produced by a mirror twin (duplicate)",
            )

    def test_stereo_forms_are_mutual(self):
        """Each emitted ``stereo_forms`` link names a real drug that links back, so an
        empty section on either form can point at the other (panel/other-forms.js)."""
        by_id = {d["id"]: d for d in self.drugs}
        linked = [d for d in self.drugs if d.get("stereo_forms")]
        self.assertIn("methylphenidate_dl",
                      by_id["methylphenidate_d"].get("stereo_forms", []))
        for d in linked:
            for other in d["stereo_forms"]:
                self.assertIn(other, by_id, f"{d['id']}: unknown stereo form {other!r}")
                self.assertIn(d["id"], by_id[other].get("stereo_forms", []),
                              f"{other} does not link back to {d['id']}")


class MetaAndTranslationsTest(unittest.TestCase):
    def test_meta_loads_with_provenance_stats(self):
        meta = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))
        self.assertIn("provenance_stats", meta)

    def test_every_receptor_family_has_a_swatch_colour(self):
        """The simulation paints a receptor bar in its transmitter's colour, reading
        meta.receptor_family_colors, so a family present in the labels but missing
        from the colours would draw a neutral grey column with no warning anywhere."""
        meta = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))
        colors = meta["receptor_family_colors"]
        self.assertEqual(set(colors), set(meta["receptor_family_labels"]))
        for family, value in colors.items():
            self.assertRegex(value, r"^#[0-9a-f]{6}$", family)
        # The transmitter colours are the ones the arrows already wear, which is the
        # whole point of the map: glutamate reads excitatory red, GABA inhibitory blue.
        self.assertEqual(colors["glutamatergic"], meta["projection_colors"]["excitatory"])
        self.assertEqual(colors["gabaergic"], meta["projection_colors"]["inhibitory"])
        self.assertEqual(colors["serotonergic"], meta["projection_colors"]["serotonergic"])

    def test_sided_name_keeps_a_proper_noun_capitalized(self):
        """Prefixing "Right"/"Left" lowers only the base name's FIRST letter. It used
        to lowercase the whole string, which ate a proper noun sitting mid-name
        ("Nucleus basalis of Meynert" -> "Right nucleus basalis of meynert")."""
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        from data_generators.i18n import _side_name
        sided = _side_name({"en": "Nucleus basalis of Meynert",
                            "fr": "Noyau basal de Meynert"}, "m", "R")
        self.assertEqual(sided["en"], "Right nucleus basalis of Meynert")
        # The ordinary common-noun case is unchanged.
        self.assertEqual(_side_name({"en": "Putamen", "fr": "Putamen"}, "m", "L")["en"],
                         "Left putamen")

    def test_metabolite_bindings_are_tallied_and_valid(self):
        """A non-modeled metabolite's receptor bindings are their own graded node kind
        (drug_metabolite_bindings), and each targets a real drug_target with a valid
        net effect, exactly like a drug binding."""
        meta = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))
        valid_targets = set(meta["drug_targets"].keys())
        # Bindings are a property of the molecule, which is ONE metabolites.jsonl record
        # whatever its parents, so the tally counts each record's bindings once.
        n_bindings = 0
        for m in _load_jsonl(DATA_DIR / "metabolites.jsonl"):
            for b in m.get("bindings", []):
                n_bindings += 1
                self.assertIn(b["target"], valid_targets,
                              f"{m['name']} binding hits unknown target {b['target']}")
                # An action binding names a functional action (the viewer derives the
                # net effect from it); an affinity-only one carries only a Ki.
                if b.get("affinity_only"):
                    self.assertIn("ki", b,
                                  f"{m['name']} affinity-only binding lacks a Ki")
                else:
                    self.assertTrue(b.get("action"),
                                    f"{m['name']} action binding lacks an action")
        kind = meta["provenance_stats"]["by_kind"].get("drug_metabolite_bindings", {})
        self.assertEqual(kind.get("total", 0), n_bindings,
                         "drug_metabolite_bindings tally != unique metabolite bindings")

    def test_binding_directions_are_their_own_node_kind(self):
        """A binding's DIRECTION is a separate node from the binding itself
        (drug_binding_action), graded by the quote sources alone.

        A measured Ki proves the ligand binds the target and says nothing about whether
        it activates or blocks it, so an affinity_only binding must read as a MISSING
        direction rather than vanish into a verified binding. Metabolite bindings are
        counted in the same kind (a ligand's binding direction either way), once per
        metabolites.jsonl record exactly like drug_metabolite_bindings.
        """
        meta = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))
        drugs = [json.loads(l) for l in
                 (DATA_DIR / "drugs.jsonl").read_text(encoding="utf-8").splitlines() if l]
        bindings = [b for d in drugs for b in d.get("bindings", [])]
        for m in _load_jsonl(DATA_DIR / "metabolites.jsonl"):
            bindings.extend(m.get("bindings", []))

        kind = meta["provenance_stats"]["by_kind"].get("drug_binding_action")
        self.assertIsNotNone(kind, "drug_binding_action missing from the tally")
        # UNKNOWN (a logged search that found nothing) sits outside the total.
        self.assertEqual(kind["total"] + kind["unknown"], len(bindings),
                         "drug_binding_action tally != drug + unique metabolite bindings")
        # No action => no direction claim at all => NOSOURCE, never a borrowed Ki grade,
        # unless a recorded search makes it UNKNOWN.
        n_affinity_only = sum(1 for b in bindings if not b.get("action"))
        n_unknown = sum(1 for b in bindings if not b.get("action") and b.get("unknown"))
        self.assertEqual(kind["unknown"], n_unknown)
        self.assertEqual(kind["nosource"], n_affinity_only - n_unknown,
                         "every unsearched affinity_only binding must count as missing")
        self.assertTrue(n_affinity_only, "expected some affinity_only bindings")
        # A direction authored with no quote behind it floors at ``llm``: weaker than a
        # quote, stronger than nothing, and not liftable by the Ki sitting beside it.
        n_llm = sum(1 for b in bindings
                    if b.get("action") and not b.get("sources"))
        self.assertEqual(kind["llm"], n_llm,
                         "a directed binding with no quote source must count as llm")
        self.assertTrue(n_llm, "expected some quote-less directed bindings")

    def test_drug_enzymes_are_tallied_and_valid(self):
        """A drug's metabolism rows are their own graded node kind (drug_enzymes), and
        each names a real enzyme / role / strength from the emitted vocabularies.

        The vocabularies ship in meta.json precisely so the viewer never hardcodes an
        isoform name, so a row pointing outside them would render as a blank label.
        """
        meta = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))
        enzymes = set(meta["enzymes"])
        roles = set(meta["enzyme_roles"])
        strengths = set(meta["enzyme_strengths"])
        drugs = [json.loads(l) for l in
                 (DATA_DIR / "drugs.jsonl").read_text(encoding="utf-8").splitlines() if l]
        n_rows = 0
        for d in drugs:
            seen = set()
            for e in d.get("enzymes", []):
                n_rows += 1
                self.assertIn(e["enzyme"], enzymes,
                              f"{d['id']} names unknown enzyme {e['enzyme']}")
                self.assertIn(e["role"], roles,
                              f"{d['id']} {e['enzyme']} has unknown role {e['role']}")
                if "strength" in e:
                    self.assertIn(e["strength"], strengths,
                                  f"{d['id']} {e['enzyme']} unknown strength")
                self.assertTrue(e.get("sources"),
                                f"{d['id']} {e['enzyme']} row carries no source")
                key = (e["enzyme"], e["role"])
                self.assertNotIn(key, seen, f"{d['id']} has a duplicate {key} row")
                seen.add(key)
        kind = meta["provenance_stats"]["by_kind"].get("drug_enzymes", {})
        self.assertEqual(kind.get("total", 0), n_rows,
                         "drug_enzymes tally != emitted enzyme rows")

    def test_metabolite_forming_enzymes_are_tallied_and_valid(self):
        """Which enzyme FORMS a metabolite is its own graded node kind
        (drug_metabolite_enzyme), one per (parent, metabolite, enzyme).

        Unlike a metabolite's bindings, this is NOT deduped by molecule: the same
        metabolite made by two parents is two reactions, two separately sourced claims.
        Every row must name a real enzyme + a real reaction verb from the emitted
        vocabularies, and must carry a source (the whole point of the kind is that only
        14 of the metabolites have one).
        """
        meta = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))
        enzymes = set(meta["enzymes"])
        reactions = set(meta["enzyme_reactions"])
        drugs = [json.loads(l) for l in
                 (DATA_DIR / "drugs.jsonl").read_text(encoding="utf-8").splitlines() if l]
        n_rows = 0
        for d in drugs:
            for m in d.get("metabolites", []):
                seen = set()
                for f in m.get("formed_by", []):
                    n_rows += 1
                    where = f"{d['id']}/{m['id']}"
                    self.assertIn(f["enzyme"], enzymes,
                                  f"{where} names unknown enzyme {f['enzyme']}")
                    if "reaction" in f:
                        self.assertIn(f["reaction"], reactions,
                                      f"{where} unknown reaction {f['reaction']}")
                    self.assertTrue(f.get("sources"),
                                    f"{where} formed_by row carries no source")
                    self.assertNotIn(f["enzyme"], seen,
                                     f"{where} has a duplicate {f['enzyme']} row")
                    seen.add(f["enzyme"])
        kind = meta["provenance_stats"]["by_kind"].get("drug_metabolite_enzyme", {})
        self.assertEqual(kind.get("total", 0), n_rows,
                         "drug_metabolite_enzyme tally != emitted formed_by rows")

    def test_translations_nonempty_and_deduped(self):
        tr = json.loads(
            (DATA_DIR / "translations.fr.json").read_text(encoding="utf-8")
        )
        self.assertIsInstance(tr, dict)
        self.assertTrue(tr, "translations.fr.json is empty")
        # The English-only refactor invariant: no key maps to itself.
        selfmapped = [k for k, v in tr.items() if k == v]
        self.assertFalse(
            selfmapped, f"translation keys mapping to themselves: {selfmapped}"
        )


    def test_search_names_bilingual_base_names_only(self):
        """search_names.fr.json maps a searchable English base name to its French
        (so "Hippocampe" finds the hippocampus from the English UI), and carries no
        per-hemisphere name: search lists one row per bilateral pair."""
        names = json.loads(
            (DATA_DIR / "search_names.fr.json").read_text(encoding="utf-8"))
        self.assertEqual(names.get("Hippocampus"), "Hippocampe")
        self.assertEqual(names.get("Frontal lobe"), "Lobe frontal")
        # receptor_effect labels too, so "Nausées" finds the Effects panel's nausea row.
        self.assertEqual(names.get("Nausea / vomiting"), "Nausées / vomissements")
        sided = [k for k in names if k.startswith(("Right ", "Left "))]
        self.assertFalse(sided, f"per-hemisphere names leaked: {sided[:5]}")
        tr = json.loads(
            (DATA_DIR / "translations.fr.json").read_text(encoding="utf-8"))
        drift = {k: v for k, v in names.items() if tr.get(k) != v}
        self.assertFalse(drift, f"search names disagree with translations: {drift}")

    def test_structure_aliases_emitted_on_both_hemispheres(self):
        recs = {json.loads(line)["id"]: json.loads(line) for line in
                (DATA_DIR / "structures.jsonl").read_text(encoding="utf-8").splitlines()}
        for sid in ("vta_R", "vta_L"):
            self.assertIn("VTA", recs[sid].get("aliases", []), sid)
        self.assertIn("LC", recs["locus_coeruleus_R"].get("aliases", []))


def _walk(node):
    """Yield every dict nested anywhere within ``node``."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


class QuoteTableTest(unittest.TestCase):
    """Guards the externalized source-quote side table (quotes.jsonl).

    Sources are emitted as ``{quote_id, provenance}`` references; the excerpts
    live once in quotes.jsonl keyed by a content hash (see quote_table.py).
    """

    @classmethod
    def setUpClass(cls):
        cls.quotes = {q["id"]: q for q in _load_jsonl(DATA_DIR / "quotes.jsonl")}
        cls.docs = [json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))]
        for name in ("structures", "projections", "circuits",
                     "projection_groups", "receptors", "drugs", "metabolites", "addons"):
            cls.docs.extend(_load_jsonl(DATA_DIR / f"{name}.jsonl"))

    def test_no_inline_quotes_remain(self):
        # Every quote-bearing source must have been externalized: no emitted dict
        # anywhere still carries an inline `quote` string (only quotes.jsonl does).
        for doc in self.docs:
            for d in _walk(doc):
                self.assertNotIn(
                    "quote", d,
                    f"inline quote survived externalization: {d!r}")

    def test_references_resolve_and_no_orphans(self):
        referenced = set()
        for doc in self.docs:
            for d in _walk(doc):
                qid = d.get("quote_id")
                if isinstance(qid, str):
                    referenced.add(qid)
                    self.assertIn(qid, self.quotes,
                                  f"quote_id {qid!r} missing from quotes.jsonl")
        orphans = set(self.quotes) - referenced
        self.assertFalse(orphans, f"orphan quotes (unreferenced): {sorted(orphans)[:3]}")

    def test_ids_are_deterministic_content_hashes(self):
        # Recompute each id from its identity fields; a mismatch means the id is
        # not a stable content hash (so it would churn across regenerations).
        for qid, q in self.quotes.items():
            src = {k: q.get(k) for k in ("corpus", "page", "quote", "species")}
            identity = json.dumps(src, sort_keys=True, ensure_ascii=False)
            digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
            self.assertEqual(qid, f"q_{digest}",
                             f"quote id {qid!r} is not its content hash")


class UncertaintyTest(unittest.TestCase):
    """The "uncertain" badge (tools/data_generators/quotes/uncertainty.py).

    The badge exists to stop a flat green check overstating a claim whose quote does
    not attribute it, so the failure mode to guard is a bullet that LOOKS sourced but
    is not: an unknown reason kind, a missing slot arg, or a blank source with no
    absence declaration (which reads to a user exactly like "the corpus is silent").

    The flags themselves are **derived**, so the other half is the two derivations: does
    a sentence attribute its claim to the drug, and does one sentence cover a family of
    subtypes without naming them. Both decide whether a real claim keeps its green
    check, so both are tested on the sentences that shaped them."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        from data_generators.quotes import uncertainty
        cls.mod = uncertainty
        cls.drugs = {d["id"]: d for d in _load_jsonl(DATA_DIR / "drugs.jsonl")}
        cls.meta = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))

    def _source(self, quote="q", page=207):
        return {"corpus": "stahl", "page": page, "quote": quote,
                "provenance": "verified"}

    def _binding(self, ki=True, target="m3"):
        b = {"target": target, "action": "antagonist", "sources": [self._source()]}
        if ki:
            b["ki"] = {"median": 25.0, "min": 1, "max": 99, "n_human": 4,
                       "n_nonhuman": 0,
                       "source": {"corpus": "pdsp_ki", "ki_id": 1,
                                  "provenance": "verified"}}
        return b

    def test_unknown_kind_raises(self):
        with self.assertRaises(KeyError):
            self.mod._uncertainty_bullet("vibes", what="x", node=self._binding(),
                                         source=self._source())

    def test_missing_slot_arg_raises(self):
        # class_wide takes {n}; without it the panel would print a literal "{n}".
        with self.assertRaises(ValueError):
            self.mod._uncertainty_bullet("class_wide", what="x",
                                         node=self._binding(),
                                         source=self._source())

    def test_sourceless_non_absence_raises(self):
        """The user's explicit requirement: a bullet cites a document or says outright
        that the corpus is silent. A silent blank is indistinguishable from the latter
        while actually meaning the source was forgotten."""
        with self.assertRaises(ValueError):
            self.mod._uncertainty_bullet("measured_ki", what="x",
                                         node=self._binding(ki=False),
                                         args={"ki": 1, "n": 1})

    def test_absence_bullet_carries_no_source(self):
        b = self.mod._uncertainty_bullet("not_a_mechanism", what="x",
                                         node=self._binding())
        self.assertTrue(b["absence"])
        self.assertNotIn("sources", b)

    def test_own_quote_bullet_cites_the_source_it_was_given(self):
        b = self.mod._uncertainty_bullet("side_effect_rule", what="x",
                                         node=self._binding(),
                                         source=self._source(page=42))
        self.assertEqual(b["sources"][0]["page"], 42)
        # ... and no source at all is an error, not a silent blank
        with self.assertRaises(ValueError):
            self.mod._uncertainty_bullet("side_effect_rule", what="x",
                                         node=self._binding())

    def test_a_sentence_attributes_its_claim_three_ways(self):
        """Naming the drug, a pronoun subject, or Stahl's elided subject. Each of these
        is a real corpus sentence that must KEEP its green check."""
        drug = {"id": "paroxetine", "name": "paroxetine"}
        for quote in ("Paroxetine's weak antimuscarinic properties can cause "
                      "constipation, dry mouth, sedation",
                      "Anticholinergic activity for paroxetine may be somewhat less "
                      "than for some other TCAs",
                      "By blocking histamine 1 receptors in the brain, it can cause "
                      "sedation and possibly weight gain",
                      "Prevents the action of acetylcholine on muscarinic receptors"):
            self.assertTrue(self.mod._attributes_to_drug(quote, drug), quote)

    def test_a_mechanism_subject_attributes_nothing(self):
        """The shape the badge exists for: the subject is the mechanism, so the sentence
        never says this drug has it."""
        drug = {"id": "nortriptyline", "name": "nortriptyline"}
        for quote in ("Blockade of alpha adrenergic 1 receptors may explain dizziness, "
                      "sedation, and hypotension",
                      "Anticholinergic activity may explain sedative effects, dry mouth, "
                      "constipation, and blurred vision",
                      "Sedative effects and weight gain may be due to antihistamine "
                      "properties"):
            self.assertFalse(self.mod._attributes_to_drug(quote, drug), quote)

    def _family_of(self, quote, targets):
        drug = {"id": "d", "name": "d", "bindings": [
            {"target": t, "sources": [self._source(quote)]} for t in targets]}
        return self.mod._family_groups(drug)

    def test_one_sentence_over_unnamed_subtypes_is_a_family_claim(self):
        """The user's nortriptyline case: Stahl writes "alpha 1", we publish A/B/D."""
        fam = self._family_of("Blockade of alpha adrenergic 1 receptors may explain "
                              "dizziness", ("alpha1a", "alpha1b", "alpha1d"))
        self.assertEqual({i: n for i, (n, _s) in fam.items()}, {0: 3, 1: 3, 2: 3})
        self.assertEqual(len(self._family_of(
            "Anticholinergic activity may explain dry mouth",
            ("m1", "m2", "m3", "m4", "m5"))), 5)

    def test_a_sentence_naming_each_subtype_is_not_one(self):
        """Three stated claims that happen to share a sentence, not one family claim.
        The spellings differ across the corpus (a bare number, a glued id), and missing
        one would publish a false doubt."""
        self.assertFalse(self._family_of(
            "Binds selectively to melatonin 1 and melatonin 2 receptors as a full "
            "agonist", ("mt1", "mt2")))
        self.assertFalse(self._family_of(
            "Blocks dopamine 3 and 4 receptors", ("d3", "d4")))
        self.assertFalse(self._family_of(
            "Has antagonist actions at serotonin 2B receptors and agonist actions at "
            "serotonin 2C receptors", ("5ht2b", "5ht2c")))
        self.assertFalse(self._family_of(
            "binding at both GABAA and GABAB receptors", ("gaba_a", "gaba_b")))

    def test_unrelated_targets_sharing_a_sentence_are_not_a_family(self):
        """A family claim is about OUR subtype split; two different receptors named in
        one sentence are two claims, however unnamed."""
        self.assertFalse(self._family_of(
            "Increases norepinephrine and especially dopamine actions by blocking "
            "their reuptake", ("dat", "net")))

    def test_every_emitted_bullet_is_sourced_or_declares_absence(self):
        kinds = set(self.meta["uncertainty_reasons"])
        seen = 0
        for d in self.drugs.values():
            for b in d.get("bindings", []):
                for u in b.get("uncertainty", []) or []:
                    seen += 1
                    self.assertIn(u["kind"], kinds)
                    self.assertTrue(u.get("sources") or u.get("absence"),
                                    f"{d['id']} {b['target']} {u['kind']}")
        self.assertGreater(seen, 0, "no uncertainty bullets emitted at all")

    # --- shape 3: the blanket pathway claim ---------------------------------------
    # The regions the derivation is exercised on, in the two forms the atlas and the
    # books disagree about (our "subthalamic nucleus" is a book's "subthalamus").
    _REGIONS = {"thalamus": "Thalamus", "frontal": "Frontal lobe",
                "caudate": "Caudate nucleus", "putamen": "Putamen",
                "cerebellum": "Cerebellum", "pons": "Pons", "midbrain": "Midbrain",
                "subthalamic_nucleus": "Subthalamic nucleus"}

    def _blanket_of(self, quote, source, targets):
        projections = [{"from": source, "to": t, "sources": [self._source(quote)]}
                       for t in targets]
        des = {b: self.mod._region_designations(b, n)
               for b, n in self._REGIONS.items()}
        return self.mod._blanket_groups(projections, des)

    def test_a_sweep_sentence_naming_no_target_is_a_blanket_claim(self):
        """The user's histamine case: Kandel writes "virtually every part of the
        neuraxis", we draw fourteen arrows."""
        g = self._blanket_of(
            "These neurons project to virtually every part of the neuraxis and play a "
            "major role in arousal.", "tuberomammillary_R",
            ("caudate_R", "putamen_R", "cerebellum"))
        self.assertEqual({i: n for i, (n, _s) in g.items()}, {0: 3, 1: 3, 2: 3})

    def test_a_named_target_keeps_its_green_check(self):
        """Only the unnamed arrows are doubted: the thalamus IS stated in this sentence,
        the cortical lobes are our split of "cerebral cortex"."""
        g = self._blanket_of(
            "The B5-B7 neurons in the pons mainly provide serotonergic innervation of "
            "the thalamus, hypothalamus, and cerebral cortex.", "raphe",
            ("thalamus_R", "frontal_R", "caudate_R"))
        self.assertEqual(sorted(g), [1, 2])

    def test_a_region_named_in_another_form_is_still_named(self):
        """A book writes "the subthalamus" for our subthalamic nucleus; missing that
        would publish a false doubt on a sentence that does name its target."""
        self.assertFalse(self._blanket_of(
            "The subthalamus receives phasic excitatory signals from the cerebral "
            "cortex, and the cerebellum as well.", "frontal_R",
            ("subthalamic_nucleus_R", "cerebellum")))

    def test_a_region_named_by_its_adjective_is_still_named(self):
        """Nieuwenhuys writes "the pontine nuclei" for a pons target; "pontine" shares
        too short a stem with "pons", so it needs its own designation or the sentence
        reads as a sweep naming nothing."""
        g = self._blanket_of(
            "The tectum, the periaqueductal grey, the pontine nuclei, the interpeduncular "
            "nucleus, and the inferior olive also receive a sizeable projection from "
            "the locus coeruleus.", "locus_coeruleus_R", ("pons", "midbrain"))
        self.assertFalse(g)

    def test_a_single_unnamed_pathway_is_not_a_sweep(self):
        """Same >= 2 rule the family claim uses: one arrow cannot establish that the
        sentence was describing a spread rather than that one target."""
        self.assertFalse(self._blanket_of(
            "These neurons project widely.", "raphe", ("caudate_R",)))

    def test_two_sources_are_two_sweeps_not_one(self):
        """Arrows leaving DIFFERENT structures never share a claim, even under one
        sentence that mentions both nuclei."""
        projections = [
            {"from": "raphe", "to": "caudate_R", "sources": [self._source("q")]},
            {"from": "locus_coeruleus_R", "to": "putamen_R",
             "sources": [self._source("q")]}]
        des = {b: self.mod._region_designations(b, n)
               for b, n in self._REGIONS.items()}
        self.assertFalse(self.mod._blanket_groups(projections, des))

    def test_every_emitted_projection_bullet_is_sourced(self):
        kinds = set(self.meta["uncertainty_reasons"])
        projections = _load_jsonl(DATA_DIR / "projections.jsonl")
        seen = 0
        for p in projections:
            for u in p.get("uncertainty", []) or []:
                seen += 1
                self.assertIn(u["kind"], kinds)
                self.assertTrue(u.get("sources") or u.get("absence"),
                                f"{p['from']}->{p['to']} {u['kind']}")
        self.assertGreater(seen, 0, "no projection uncertainty bullets emitted at all")
        c = self.meta["provenance_stats"]["by_kind"]["projections"]
        self.assertEqual(c["uncertain"],
                         sum(1 for p in projections if p.get("uncertainty")))

    def test_the_flagged_nodes_leave_verified_but_stay_backed(self):
        """The agreed tally rule: `uncertain` is its own bucket out of `verified`, and
        the headline is unchanged because a real document does exist."""
        c = self.meta["provenance_stats"]["by_kind"]["drug_bindings"]
        flagged = sum(1 for d in self.drugs.values() for b in d.get("bindings", [])
                      if b.get("uncertainty"))
        self.assertEqual(c["uncertain"], flagged)
        self.assertEqual(c["verified"] + c["uncertain"] + c["sourced"] + c["missing"],
                         c["total"])
        a = self.meta["provenance_stats"]["nodes"]
        self.assertEqual(a["backed"], a["verified"] + a["uncertain"] + a["sourced"])


class AddonTest(unittest.TestCase):
    """Addon nodes (tools/data_generators/addons.py): the kind that carries its own
    insertion point.

    Its distinctive failure mode is *silent*: a node that is well-formed, graded and
    counted in the tally, but anchored somewhere no panel ever looks, so it simply
    never appears. Nothing downstream can notice that, which is why the slot /
    display / tone vocabularies are closed and validated at generation. These tests
    guard that contract from both ends: the emitted records agree with the emitted
    registry, and each validator really raises."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        from data_generators import addons
        cls.mod = addons
        cls.addons = _load_jsonl(DATA_DIR / "addons.jsonl")
        cls.meta = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))

    def _authored(self, **patch):
        base = {"id": "t", "owner_kind": "drug", "owner": "mdma",
                "slot": "drug.metabolism", "display": "admonition",
                "tone": "caution", "text": {"en": "x", "fr": "x"}, "sources": []}
        base.update(patch)
        return base

    def test_every_emitted_addon_fits_the_emitted_registry(self):
        slots = self.meta["addon_slots"]
        displays = set(self.meta["addon_displays"])
        tones = set(self.meta["addon_tones"])
        self.assertTrue(self.addons, "no addon nodes emitted at all")
        for a in self.addons:
            self.assertIn(a["slot"], slots)
            self.assertEqual(slots[a["slot"]], a["owner_kind"],
                             f"addon {a['id']} anchors the wrong node kind for its slot")
            self.assertIn(a["display"], displays)
            self.assertIn(a["tone"], tones)
            self.assertTrue(a.get("text"), f"addon {a['id']} states no claim")

    def test_ids_are_unique(self):
        ids = [a["id"] for a in self.addons]
        self.assertEqual(len(ids), len(set(ids)))

    def test_an_unknown_slot_display_or_tone_raises(self):
        for patch in ({"slot": "drug.nowhere"}, {"display": "popup"},
                      {"tone": "shouting"}):
            with self.assertRaises(KeyError):
                self.mod._addon_record(self._authored(**patch))

    def test_anchoring_the_wrong_node_kind_for_a_slot_raises(self):
        # A receptor addon in a drug slot would be looked up under a key no panel
        # ever builds, so it would ship and never draw.
        with self.assertRaises(KeyError):
            self.mod._addon_record(self._authored(owner_kind="receptor"))

    def test_a_claimless_addon_raises(self):
        with self.assertRaises(KeyError):
            self.mod._addon_record(self._authored(text=None))

    def test_every_slot_has_a_call_site_in_the_viewer(self):
        # The rule the whole kind rests on: a slot the viewer never asks for swallows
        # its node silently (well-formed, graded, counted, never drawn). Nothing at
        # runtime can notice that, so it is checked here, by looking for the slot's
        # literal in the viewer's modules.
        js = "\n".join(p.read_text(encoding="utf-8")
                       for p in sorted((REPO_ROOT / "public" / "js").rglob("*.js")))
        for slot in self.meta["addon_slots"]:
            self.assertIn(f'"{slot}"', js,
                          f"slot {slot!r} has no appendAddons() call site in the viewer")

    def test_a_section_addon_anchors_a_registered_section(self):
        # A section anchor is the one owner kind with no node behind it (the claim is
        # about a whole view), so the emitted vocabulary is what stands in for the id
        # pool: an owner outside it would be drawn by nothing.
        sections = self.meta["addon_sections"]
        self.assertTrue(sections, "no addon sections emitted")
        anchored = [a for a in self.addons if a["owner_kind"] == "section"]
        self.assertTrue(anchored, "the bilaterality caveat is a section addon")
        for a in anchored:
            self.assertIn(a["owner"], sections)

    def test_the_bilaterality_caveat_is_deliberately_sourceless(self):
        # Its claim IS that nothing sources the mirroring, so a citation on it would
        # contradict its own text. It must read as NOSOURCE, not as an llm guess.
        a = next(x for x in self.addons if x["id"] == "projection_bilaterality")
        self.assertEqual(a["sources"], [])
        self.assertEqual(a["slot"], "section.projections")

    def test_dataset_statements_are_flagged_not_left_as_nosource(self):
        # A statement about the dataset itself (its coverage, its mirroring) cannot be
        # sourced, so it must say so through the closed basis vocabulary instead of
        # drawing the red NOSOURCE pill a merely-unsourced claim gets.
        self.assertIn("dataset", self.meta["addon_bases"])
        by_id = {a["id"]: a for a in self.addons}
        for aid in ("projection_bilaterality", "enzyme_list_not_exhaustive"):
            self.assertEqual(by_id[aid]["basis"], "dataset", aid)
        for a in self.addons:
            self.assertIn(a["basis"], self.meta["addon_bases"])

    def test_an_unknown_or_sourced_dataset_basis_raises(self):
        with self.assertRaises(KeyError):
            self.mod._addon_record(self._authored(basis="opinion"))
        src = {"corpus": "stahl", "page": 1, "quote": "x", "provenance": "verified"}
        with self.assertRaises(KeyError):
            self.mod._addon_record(self._authored(basis="dataset", sources=[src]))

    def test_the_tally_counts_them_as_nodes(self):
        # Knowledge addons only: a dataset statement is not a node of the tally.
        c = self.meta["provenance_stats"]["by_kind"]["addons"]
        claims = [a for a in self.addons if a["basis"] != "dataset"]
        self.assertEqual(c["total"], len(claims))
        self.assertEqual(c["verified"] + c["uncertain"] + c["sourced"] + c["missing"],
                         c["total"])


class ContradictionTest(unittest.TestCase):
    """The ``contradicted`` badge (tools/data_generators/quotes/contradictions.py): one
    hand-written table keyed by citation site, one apply pass over every node kind.

    Unlike the derived uncertainty flags its failure mode is a *stale* entry: a fetcher
    re-run drops the node an entry doubts and the contradiction silently marks nothing.
    The applier raises instead, and these tests hold it to that, to the precision of the
    site (a sub-claim, one binding of two on a target), and to the tally contract."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        sys.path.insert(0, str(REPO_ROOT / "tools" / "sourcing"))
        sys.path.insert(0, str(REPO_ROOT / "tools" / "fetch"))
        import citation_site as CS
        from data_generators.quotes import contradictions, uncertainty
        cls.CS = CS
        cls.table = contradictions.CONTRADICTIONS
        cls.uncertainty = uncertainty
        cls.drugs = _load_jsonl(DATA_DIR / "drugs.jsonl")
        cls.receptors = {r["id"]: r for r in _load_jsonl(DATA_DIR / "receptors.jsonl")}
        cls.meta = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))
        cls.nodes, cls.ambiguous = CS.node_index(
            drugs=cls.drugs, metabolites=_load_jsonl(DATA_DIR / "metabolites.jsonl"),
            receptors=list(cls.receptors.values()), targets=cls.meta["drug_targets"],
            projections=_load_jsonl(DATA_DIR / "projections.jsonl"))
        cls.quotes = {q["id"]: q for q in _load_jsonl(DATA_DIR / "quotes.jsonl")}

    def _sites(self, fragment):
        return [k for k in self.table if fragment in k]

    def test_every_entry_lands_on_its_node_citing_the_denial(self):
        self.assertTrue(self.table, "no contradictions curated at all")
        for key, entry in self.table.items():
            self.assertNotIn(key, self.ambiguous, f"{key} names two nodes")
            self.assertIn(key, self.nodes, f"{key} names no emitted node")
            bullets = [b for b in self.nodes[key].get("uncertainty", [])
                       if b["kind"] == "contradicted"]
            self.assertEqual(len(bullets), 1, f"{key} carries no (or two) badges")
            # A quote by its id; a PDSP CSV row (no prose) by its row number.
            cited = [self.quotes[s["quote_id"]]["quote"] if "quote_id" in s else s["ki_id"]
                     for s in bullets[0]["sources"]]
            want = [s.get("quote", s.get("ki_id"))
                    for s in self.uncertainty.contradicted_sources(entry)]
            self.assertEqual(cited, want, f"{key} bullet does not cite the denial")

    def test_the_migrated_entries_kept_their_sites(self):
        # One per kind the five per-kind tables used to hold (binding, metabolite link,
        # enzyme row, enzyme tier, receptor attribute).
        for key in ("drug:etomidate/bindings[gaba_a:modulator]",
                    "drug:olanzapinesamidorphan/metabolites[samidorphan_n_oxide]",
                    "drug:fluoxetine/enzymes[cyp3a4:inhibitor]",
                    "drug:sertraline/enzymes[cyp2d6:inhibitor]/strength",
                    "receptor:5ht5a/classification[synaptic]"):
            self.assertIn(key, self.table)

    def test_one_binding_of_two_on_a_target(self):
        # Amisulpride antagonises D2 and (tentatively) partially agonises it: the denial
        # is of the second, so the first must stay unflagged.
        part = "drug:amisulpride/bindings[d2:partial_agonist]"
        self.assertIn(part, self.table)
        anta = self.nodes["drug:amisulpride/bindings[d2:antagonist]"]
        self.assertNotIn("contradicted", [b["kind"] for b in anta.get("uncertainty", [])])

    def test_receptor_bullet_rides_on_the_attribute_only(self):
        for key in self._sites("/classification["):
            rid = key.split(":", 1)[1].split("/", 1)[0]
            attr = key.rsplit("[", 1)[1].rstrip("]")
            for other, entry in self.receptors[rid]["classification"].items():
                if other != attr and f"receptor:{rid}/classification[{other}]" not in self.table:
                    self.assertFalse(entry.get("uncertainty"), f"{rid}/{other} leaked")

    def test_strength_bullet_rides_on_the_tier_not_the_row(self):
        for key in self._sites("]/strength"):
            self.assertFalse(self.nodes[key[:-len("/strength")]].get("uncertainty"),
                             f"{key}: the row itself is flagged")

    def test_a_flagged_enzyme_row_buckets_as_uncertain(self):
        c = self.meta["provenance_stats"]["by_kind"]["drug_enzymes"]
        flagged = sum(1 for d in self.drugs for e in d.get("enzymes", []) or []
                      if e.get("uncertainty"))
        self.assertEqual(c["uncertain"], flagged)
        rows = [k for k in self._sites("/enzymes[") if not k.endswith("/strength")]
        self.assertEqual(flagged, len(rows))

    def test_an_llm_claim_denied_stays_missing(self):
        for kind, attr in (("receptor_sign", "sign"), ("receptor_synaptic", "synaptic")):
            entries = [r["classification"][attr] for r in self.receptors.values()
                       if (r.get("ubiquitous") or r.get("locations")
                           or r.get("description"))]
            backed_flagged = sum(1 for e in entries if e.get("uncertainty")
                                 and e["grade"] in ("verified", "sourced"))
            c = self.meta["provenance_stats"]["by_kind"][kind]
            self.assertEqual(c["uncertain"], backed_flagged, kind)

    def test_the_reason_kind_is_in_the_emitted_vocabulary(self):
        self.assertIn("contradicted", self.meta["uncertainty_reasons"])

    def _apply(self, table, **records):
        self.uncertainty.apply_contradictions(*self.CS.node_index(**records), table=table)

    def test_any_node_kind_can_be_contradicted(self):
        src = {"corpus": "wikipedia_pharm", "page": "x", "quote": "q", "provenance": "verified"}
        drug = {"id": "x", "workup": [{"test": "ecg", "timing": "before", "sources": []}],
                "bindings": [{"target": "d2", "action": "antagonist"},
                             {"target": "d2", "action": "partial_agonist"}]}
        rec = {"id": "h1", "classification": {},
               "effects": [{"mode": "antagonism", "effect": "sedation", "sources": []}]}
        met = {"id": "m", "bindings": [{"target": "h1", "action": "antagonist"}]}
        self._apply({"drug:x/workup[ecg:before]": src,
                     "drug:x/bindings[d2:partial_agonist]": [src, src],
                     "receptor:h1/effects[antagonism:sedation]": src,
                     "metabolite:m/bindings[h1:antagonist]": src},
                    drugs=[drug], receptors=[rec], metabolites=[met])
        self.assertEqual(drug["workup"][0]["uncertainty"][0]["kind"], "contradicted")
        self.assertNotIn("uncertainty", drug["bindings"][0])
        self.assertEqual(len(drug["bindings"][1]["uncertainty"][0]["sources"]), 2)
        self.assertEqual(rec["effects"][0]["uncertainty"][0]["kind"], "contradicted")
        self.assertEqual(met["bindings"][0]["uncertainty"][0]["kind"], "contradicted")

    def test_the_bullet_is_appended_not_assigned(self):
        derived = {"kind": "family_claim"}
        drug = {"id": "etomidate", "bindings": [{"target": "gaba_a", "action": "modulator",
                                                 "sources": [], "uncertainty": [derived]}]}
        src = self.table["drug:etomidate/bindings[gaba_a:modulator]"]
        self._apply({"drug:etomidate/bindings[gaba_a:modulator]": src}, drugs=[drug])
        kinds = [b["kind"] for b in drug["bindings"][0]["uncertainty"]]
        self.assertEqual(kinds, ["family_claim", "contradicted"])

    def test_a_site_with_nothing_to_contradict_raises(self):
        src = {"corpus": "wikipedia_pharm", "page": "x", "quote": "q", "provenance": "verified"}
        cases = [
            # the node is gone (a fetcher re-run dropped the row)
            ({"drug:fluoxetine/enzymes[cyp3a4:inhibitor]": src},
             {"drugs": [{"id": "fluoxetine", "enzymes": []}]}),
            # a flat *_sources facet has no node dict to carry the bullet
            ({"drug:x/half_life": src},
             {"drugs": [{"id": "x", "half_life": {"hours": 3}, "half_life_sources": []}]}),
            # two rows at one site: the bullet would land on an arbitrary one
            ({"drug:x/bindings[d2:antagonist]": src},
             {"drugs": [{"id": "x", "bindings": [{"target": "d2", "action": "antagonist"},
                                                 {"target": "d2", "action": "antagonist"}]}]}),
        ]
        for table, records in cases:
            with self.subTest(next(iter(table))), self.assertRaises(KeyError):
                self._apply(table, **records)

    def test_a_quote_label_is_never_a_tmax_source(self):
        # fetch_tmax reads only dailymed_labels.json: a combination label stored for one
        # quote must stay out of it, or its kinetics would be published as one drug's.
        import fetch_dailymed
        chosen = json.loads(fetch_dailymed.CACHE_PATH.read_text(encoding="utf-8"))
        cited = {src["page"] for entry in self.table.values()
                 for src in self.uncertainty.contradicted_sources(entry)
                 if src["corpus"] == "dailymed"}
        self.assertTrue(cited <= set(fetch_dailymed.QUOTE_LABELS))
        self.assertFalse({m["setid"] for m in chosen.values()} & set(fetch_dailymed.QUOTE_LABELS))

if __name__ == "__main__":
    unittest.main(verbosity=2)


class ProjectionClaimTest(unittest.TestCase):
    """The pathway per-claim split (tools/data_generators/quotes/attestation.py).

    An arrow asserts three things at once (the pathway exists, it carries transmitter X,
    its sign is Y) and used to publish all three under one grade, so a sentence stating
    only the route also green-checked the transmitter and the sign that colours the arrow
    in Potential mode. The failure mode to guard is therefore a sub-claim that LOOKS
    attested: a source kept on a claim its quote never names, or a grade above the base
    one with nothing behind it."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        from data_generators.quotes import attestation
        cls.mod = attestation
        cls.projections = _load_jsonl(DATA_DIR / "projections.jsonl")
        cls.drugs = _load_jsonl(DATA_DIR / "drugs.jsonl")

    def _proj(self, kind, nt, quote):
        return {"from": "a_R", "to": "b_R", "kind": kind, "neurotransmitter": nt,
                "sources": [{"corpus": "kandel", "page": 1, "quote": quote,
                             "provenance": "verified"}]}

    def test_a_naming_quote_grades_the_claim_and_keeps_only_its_own_source(self):
        p = self._proj("excitatory", "Glutamate",
                       "The corticostriatal projection is excitatory (glutamatergic).")
        self.mod.apply_projection_claims([p])
        self.assertEqual(p["claims"]["transmitter"]["grade"], "verified")
        self.assertEqual(p["claims"]["sign"]["grade"], "verified")
        self.assertEqual(len(p["claims"]["sign"]["sources"]), 1)

    def test_a_route_only_quote_attests_neither_part(self):
        """The whole point: stating the arrow is not stating what rides it."""
        p = self._proj("excitatory", "Glutamate",
                       "The frontal cortex projects to the putamen.")
        self.mod.apply_projection_claims([p])
        for claim in ("transmitter", "sign"):
            self.assertEqual(p["claims"][claim]["grade"], self.mod.BASE_GRADE)
            self.assertNotIn("sources", p["claims"][claim])

    def test_a_modulatory_pathway_makes_no_sign_claim_at_all(self):
        """"Modulatory" is the ABSENCE of a sign claim, not an unsourced third value."""
        p = self._proj("histaminergic", "Histamine",
                       "The tuberomammillary nucleus is the sole source of histamine.")
        self.mod.apply_projection_claims([p])
        self.assertNotIn("sign", p["claims"])
        self.assertEqual(p["claims"]["transmitter"]["grade"], "verified")

    def test_a_transmitter_with_no_word_test_raises(self):
        """A new system must say how a sentence would attest it, or it never could."""
        p = self._proj("excitatory", "Unobtainium", "Some sentence.")
        with self.assertRaises(KeyError):
            self.mod.apply_projection_claims([p])

    def test_an_enzyme_row_states_its_tier_or_makes_no_claim(self):
        """The metabolism twin: the CYP gate checks the isoform, never the tier."""
        def row(strength, quote):
            return {"id": "d", "enzymes": [{"enzyme": "cyp3a4", "role": "substrate",
                    **({"strength": strength} if strength else {}),
                    "sources": [{"corpus": "stahl", "page": 1, "quote": quote,
                                 "provenance": "verified"}]}]}
        named = row("major", "Fluoxetine is a major substrate of CYP3A4.")
        self.mod.apply_enzyme_strength_claims([named])
        self.assertEqual(named["enzymes"][0]["claims"]["strength"]["grade"], "verified")

        silent = row("major", "Fluoxetine is metabolized by CYP3A4.")
        self.mod.apply_enzyme_strength_claims([silent])
        entry = silent["enzymes"][0]["claims"]["strength"]
        self.assertEqual(entry["grade"], self.mod.BASE_GRADE)
        self.assertNotIn("sources", entry)

        # The words the corpora state a tier by attest it; an overall extent of
        # metabolism or a bare percentage does not, a reader would have to infer the tier.
        for strength, quote, grade in (
                ("major", "Metabolized mainly by CYP2D6 and CYP1A2", "verified"),
                ("major", "Domperidone is almost exclusively metabolized by CYP3A4", "verified"),
                ("major", "in the human body CYP2C19 plays the most important role", "verified"),
                ("minor", "and to a lesser extent by CYP3A4", "verified"),
                ("weak", "Induces CYP3A4 (and slightly CYP1A2 and CYP2B6)", "verified"),
                ("major", "Extensively metabolized by CYP2D6 and CYP3A", self.mod.BASE_GRADE),
                ("minor", "Liver through CYP3A4 (~60%), CYP2C9 (~20%)", self.mod.BASE_GRADE)):
            r = row(strength, quote)
            self.mod.apply_enzyme_strength_claims([r])
            self.assertEqual(r["enzymes"][0]["claims"]["strength"]["grade"], grade, quote)
        # A row with no tier asserts nothing about it, so it gets no node at all.
        tierless = row(None, "Fluoxetine is metabolized by CYP3A4.")
        self.mod.apply_enzyme_strength_claims([tierless])
        self.assertNotIn("claims", tierless["enzymes"][0])

    def test_the_emitted_data_carries_one_claim_per_pathway(self):
        signed = {"excitatory", "inhibitory"}
        for p in self.projections:
            claims = p.get("claims") or {}
            self.assertIn("transmitter", claims, f"{p['from']}->{p['to']}")
            self.assertEqual("sign" in claims, p["kind"] in signed,
                             f"{p['from']}->{p['to']} sign claim vs kind {p['kind']!r}")
            for name, entry in claims.items():
                if not entry.get("sources"):
                    self.assertEqual(entry["grade"], self.mod.BASE_GRADE,
                                     f"{p['from']}->{p['to']} {name} graded with no source")

    def test_the_emitted_enzyme_rows_carry_a_claim_exactly_when_they_state_a_tier(self):
        for d in self.drugs:
            for e in d.get("enzymes") or []:
                entry = (e.get("claims") or {}).get("strength")
                self.assertEqual(bool(entry), bool(e.get("strength")),
                                 f"{d['id']} {e['enzyme']} tier vs claim")
                if entry and not entry.get("sources"):
                    self.assertEqual(entry["grade"], self.mod.BASE_GRADE)
