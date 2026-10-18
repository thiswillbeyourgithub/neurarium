"""Family 5: a binding's ``ki`` cites one CSV row by ki_id (the analogue of a quote's
page): confirm that row really exists in the corpus CSV with the cited value.

Like the quote gate this is author-side (the CSV is large + uncommitted, see
data_sources/books/pdsp_ki/), skipped with a warning on a clone that lacks it.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

import csv

from ..common import REPO_ROOT


class KiGate:
    """The PDSP-CSV row checks, plus the state they accumulate."""

    def __init__(self, report, corpora):
        self.report = report
        self.corpora = corpora
        self.index_cache = {}    # corpus -> {ki_id: ki_val_str} or None if csv absent
        self.n_ki = 0
        self.skipped = set()

    def ki_index(self, corpus):
        if corpus not in self.index_cache:
            entry = self.corpora.get(corpus) or {}
            path = entry.get("csv")
            idx = None
            if path and (REPO_ROOT / path).exists():
                idx = {}
                with open(REPO_ROOT / path, newline="", encoding="utf-8",
                          errors="replace") as f:
                    for row in csv.DictReader(f):
                        try:
                            idx[int(row["Number"])] = (row.get("ki Val") or "").strip()
                        except (TypeError, ValueError, KeyError):
                            pass
            self.index_cache[corpus] = idx
        return self.index_cache[corpus]

    def check_ki_source(self, ctx, src):
        """Gate one source citing a PDSP-CSV row by ki_id: a binding's Ki, or an
        uncertainty bullet's measurement (a curated denial included)."""
        report = self.report
        corpus, ki_id = src.get("corpus"), src.get("ki_id")
        # Only a CSV corpus (PDSP) cites a row by ki_id; a quote-gated Ki corpus
        # (wikipedia_pharm) was already verified by the source-quote gate.
        if not (self.corpora.get(corpus) or {}).get("csv"):
            return
        if src.get("provenance") == "verified" and ki_id is None:
            report.error(f"{ctx}: 'verified' source needs a ki_id")
            return
        if ki_id is None:
            return
        idx = self.ki_index(corpus)
        if idx is None:
            self.skipped.add(corpus)
            return
        if ki_id not in idx:
            report.error(f"{ctx}: ki_id {ki_id} not found in {corpus} CSV")
            return
        # The stored value must be the row's own value (we took it from there).
        try:
            if abs(float(idx[ki_id]) - float(src.get("value_nm"))) > 0.01:
                report.error(f"{ctx}: value_nm {src.get('value_nm')} != CSV row "
                             f"{ki_id} value {idx[ki_id]!r}")
                return
        except (TypeError, ValueError):
            pass
        self.n_ki += 1

    def check_bullet_ki(self, ctx, node):
        """The CSV-row sources of a node's uncertainty bullets, which the bullet gate
        (``QuoteGate.check_uncertainty``) hands over to this family."""
        for j, u in enumerate(node.get("uncertainty") or []):
            for k, src in enumerate(u.get("sources") or []):
                if src.get("ki_id") is not None:
                    self.check_ki_source(f"{ctx} uncertainty[{j}] sources[{k}]", src)

    def check_ki(self, ctx, binding):
        """Gate one binding's PDSP-CSV Ki (a metabolite binding's Ki is checked the same
        way as a drug's) and its bullets' CSV rows."""
        self.check_ki_source(f"{ctx} ki", (binding.get("ki") or {}).get("source") or {})
        self.check_bullet_ki(ctx, binding)


def check_ki_rows(ki, drugs, metabolites):
    """Every drug and metabolite binding's CSV-row Ki, then the verdict."""
    report = ki.report
    ki_before = report.errors
    for drug in drugs:
        did = drug.get("id")
        for binding in drug.get("bindings", []):
            ki.check_ki(f"drug {did} binding {binding.get('target')}", binding)
    for m in metabolites:
        for binding in m.get("bindings", []) or []:
            ki.check_ki(f"metabolite {m.get('id')} binding {binding.get('target')}",
                        binding)
    if ki.skipped:
        report.warn(f"Ki CSV absent for {sorted(ki.skipped)} (author-only material); "
                    f"skipped the ki-row-in-CSV check there")
    if report.errors == ki_before:
        report.ok(f"every checkable Ki annotation ({ki.n_ki}) cites a real CSV row"
                  if ki.n_ki else "no Ki annotations to verify yet")
