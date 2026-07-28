#!/usr/bin/env python
"""Test harness guarding tools/generate_data.py.

Stdlib unittest only (no deps). Runnable directly:

    python tools/tests/test_generate.py

Also pytest-discoverable. Two families of test:

* **Golden**: regenerate the dataset into a scratch dir via
  ``generate_data.py --root <tmp>`` and assert every emitted file is
  byte-identical to the committed baseline under ``public/data/``. This is the
  load-bearing guard for the upcoming split of ``generate_data.py``: a pure
  refactor must keep the output bytes unchanged.
* **Data-integrity**: read the *emitted* files under ``public/data/`` (never
  import generator internals) so these assertions survive the refactor.
"""

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "public" / "data"
GENERATOR = REPO_ROOT / "tools" / "generate_data.py"


def _load_jsonl(path):
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _rel_files(base):
    """Every regular file under ``base``, as paths relative to ``base``."""
    return {p.relative_to(base) for p in base.rglob("*") if p.is_file()}


class GoldenTest(unittest.TestCase):
    """Regenerating must reproduce the committed public/data byte-for-byte."""

    def test_golden_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = subprocess.run(
                [sys.executable, str(GENERATOR), "--root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"generator failed:\n{proc.stdout}\n{proc.stderr}",
            )

            gen_dir = root / "data"
            self.assertTrue(gen_dir.is_dir(), "generator wrote no data/ dir")

            committed = _rel_files(DATA_DIR)
            generated = _rel_files(gen_dir)

            # public/data also holds vendored, non-generated assets (molecules/,
            # a .claude/ dir). Restrict the comparison to what the generator
            # actually emits, but require it to emit no *fewer* of those.
            missing = generated - committed
            self.assertFalse(
                missing,
                f"generator emitted files absent from public/data: {sorted(map(str, missing))}",
            )

            mismatched = []
            for rel in sorted(generated):
                a = (gen_dir / rel).read_bytes()
                b = (DATA_DIR / rel).read_bytes()
                if a != b:
                    mismatched.append(str(rel))
            self.assertFalse(
                mismatched,
                "regenerated files differ from committed baseline: "
                f"{mismatched}",
            )


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


class MetaAndTranslationsTest(unittest.TestCase):
    def test_meta_loads_with_provenance_stats(self):
        meta = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))
        self.assertIn("provenance_stats", meta)

    def test_metabolite_bindings_are_tallied_and_valid(self):
        """A non-modeled metabolite's receptor bindings are their own graded node kind
        (drug_metabolite_bindings), and each targets a real drug_target with a valid
        net effect, exactly like a drug binding."""
        meta = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))
        valid_targets = set(meta["drug_targets"].keys())
        drugs = [json.loads(l) for l in
                 (DATA_DIR / "drugs.jsonl").read_text(encoding="utf-8").splitlines() if l]
        # A metabolite produced by several drugs appears once under EACH parent with
        # identical bindings; those bindings are a property of the molecule, so the tally
        # counts them ONCE per unique metabolite (deduped by folded name), not per parent.
        # Mirror that dedup here so the count matches the tally even if a shared
        # metabolite is added later.
        seen_metab = set()
        n_bindings = 0
        for d in drugs:
            for m in d.get("metabolites", []):
                key = re.sub(r"[^a-z0-9]", "", (m.get("name") or "").lower())
                first_occurrence = key not in seen_metab
                seen_metab.add(key)
                for b in m.get("bindings", []):
                    if first_occurrence:
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
                    where = f"{d['id']}/{m['name']}"
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
                     "projection_groups", "receptors", "drugs"):
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
            self.mod._uncertainty_bullet("vibes", what="x", binding=self._binding(),
                                         source=self._source())

    def test_missing_slot_arg_raises(self):
        # class_wide takes {n}; without it the panel would print a literal "{n}".
        with self.assertRaises(ValueError):
            self.mod._uncertainty_bullet("class_wide", what="x",
                                         binding=self._binding(),
                                         source=self._source())

    def test_sourceless_non_absence_raises(self):
        """The user's explicit requirement: a bullet cites a document or says outright
        that the corpus is silent. A silent blank is indistinguishable from the latter
        while actually meaning the source was forgotten."""
        with self.assertRaises(ValueError):
            self.mod._uncertainty_bullet("measured_ki", what="x",
                                         binding=self._binding(ki=False),
                                         args={"ki": 1, "n": 1})

    def test_absence_bullet_carries_no_source(self):
        b = self.mod._uncertainty_bullet("not_a_mechanism", what="x",
                                         binding=self._binding())
        self.assertTrue(b["absence"])
        self.assertNotIn("sources", b)

    def test_own_quote_bullet_cites_the_source_it_was_given(self):
        b = self.mod._uncertainty_bullet("side_effect_rule", what="x",
                                         binding=self._binding(),
                                         source=self._source(page=42))
        self.assertEqual(b["sources"][0]["page"], 42)
        # ... and no source at all is an error, not a silent blank
        with self.assertRaises(ValueError):
            self.mod._uncertainty_bullet("side_effect_rule", what="x",
                                         binding=self._binding())

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
