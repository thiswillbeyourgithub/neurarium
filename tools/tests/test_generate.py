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
    # Pinned regression guard (verified against the real data 2026-07).
    EXPECTED_FAMILIES = {
        "serotonergic": 13,
        "adrenergic": 11,
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
        self.assertEqual(len(self.receptors), 63)
        ids = [r["id"] for r in self.receptors]
        self.assertEqual(len(set(ids)), 63, "receptor ids are not unique")

    def test_family_distribution(self):
        counts = {}
        for r in self.receptors:
            counts[r["family"]] = counts.get(r["family"], 0) + 1
        self.assertEqual(counts, self.EXPECTED_FAMILIES)
        self.assertEqual(sum(counts.values()), 63)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
