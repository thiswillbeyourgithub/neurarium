"""Family 12: metabolizer-status profiles, re-derived from the pinned PharmFreq export.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

from pathlib import Path

# The PharmFreq export reader, imported rather than restated: family 12
# rebuilds the emitted quotes with the very code that wrote them, which is
# the whole point of the derivation gate (see data_generators/pharmfreq.py).
from data_generators import pharmfreq

from .common import REPO_ROOT
from .cpic_guidance import check_cpic_guidance


def check_enzyme_variability(report, meta, drugs):
    """Family 12: the metabolizer-status profiles, re-derived from their pinned tables.

    Every other corpus proves a quote by finding it verbatim in prose somebody else
    wrote. PharmFreq (corpus #13) publishes a table instead, and the sentence a reader
    sees is one this repo composes out of it, so there is no page to look in: writing
    that sentence to a page file and then finding it there would prove only that the
    same code ran twice.

    So the proof runs the other way. The export is committed under `tools/data/`
    (small, freely redistributable, unlike the books), the cache that built the profiles
    pins each file's sha256, and this rebuilds every emitted profile and quote straight
    off those files. A hand-edited frequency, a stale cache, a refreshed download nobody
    re-ran the fetcher over: each one lands here as an error, on any clone, with no
    author-side material needed.
    """
    report.header("12. Enzyme variability (profiles re-derived from the pinned export)")
    corpora = meta.get("source_corpora") or {}
    tsv_corpora = {c: e for c, e in corpora.items() if e.get("tsv_dir")}
    if not tsv_corpora:
        report.ok("no committed-table corpus to re-derive")
        return
    for corpus, entry in sorted(tsv_corpora.items()):
        export = REPO_ROOT / entry["tsv_dir"]
        if not export.is_dir():
            report.error(f"{corpus}: {entry['tsv_dir']} is missing, yet the corpus is "
                         f"committed with the repo (its quotes cannot be re-derived)")
            return
        pins = entry.get("export_sha256") or {}
        if not pins:
            report.error(f"{corpus}: declares {entry['tsv_dir']} but pins no file "
                         f"sha256, so nothing anchors its quotes")
            return
        # Every file that looks like part of this export, by the extension the pins
        # themselves use (PharmFreq ships TSVs, CPIC one JSON), so a new sibling data
        # file nothing anchors is caught while the dir's README is left alone.
        suffixes = {Path(name).suffix for name in pins}
        on_disk = {p.name for p in export.iterdir()
                   if p.is_file() and p.suffix in suffixes}
        fetcher = f"tools/fetch/fetch_{corpus}.py"
        for name in sorted(set(pins) | on_disk):
            if name not in on_disk:
                report.error(f"{corpus}: pins {name}, which is not in "
                             f"{entry['tsv_dir']}")
            elif name not in pins:
                report.error(f"{corpus}: {entry['tsv_dir']}/{name} is not pinned "
                             f"(re-run {fetcher})")
            elif pharmfreq.sha256(str(export / name)) != pins[name]:
                report.error(f"{corpus}: {entry['tsv_dir']}/{name} no longer hashes to "
                             f"its pin, so the emitted numbers are not the ones in it "
                             f"(re-run {fetcher})")
        if report.errors:
            return

    export = REPO_ROOT / tsv_corpora["pharmfreq"]["tsv_dir"]
    try:
        raw = pharmfreq.read_export(str(export))
    except pharmfreq.ExportError as exc:
        report.error(f"pharmfreq: {exc}")
        return

    n = 0
    for eid, enzyme in sorted((meta.get("enzymes") or {}).items()):
        var = enzyme.get("variability")
        if not var:
            continue
        gene = var.get("gene")
        ctx = f"enzyme {eid} variability"
        if gene not in raw:
            report.error(f"{ctx}: cites gene {gene!r}, which the export does not cover")
            continue
        if pharmfreq.GENE_ENZYMES.get(gene) != eid:
            report.error(f"{ctx}: gene {gene!r} is mapped to "
                         f"{pharmfreq.GENE_ENZYMES.get(gene)!r}, not to {eid!r}")
            continue
        want_profile = pharmfreq.ordered_profile(raw[gene])
        if var.get("profile") != want_profile:
            report.error(f"{ctx}: the emitted profile is not what {gene} reads in the "
                         f"export (re-run tools/fetch/fetch_pharmfreq.py)")
            continue
        # Key order is deliberately NOT checked: the viewer walks
        # `meta.metabolizer_groups` and looks each group up, so the profile is a
        # mapping and the cache is free to serialize it sorted.
        want_quote = pharmfreq.quote_for(gene, want_profile)
        srcs = var.get("sources") or []
        if not srcs:
            report.error(f"{ctx}: carries a profile but no source")
            continue
        for i, src in enumerate(srcs):
            if src.get("page") != gene:
                report.error(f"{ctx} sources[{i}]: page {src.get('page')!r} is not the "
                             f"gene symbol {gene!r} the profile is keyed by")
            if src.get("quote") != want_quote:
                report.error(f"{ctx} sources[{i}]: the quote is not the one the export "
                             f"yields for {gene} (re-run tools/fetch/fetch_pharmfreq.py)")
            else:
                n += 1

    covered = {eid for eid, e in (meta.get("enzymes") or {}).items()
               if e.get("variability")}
    uncovered = sorted(set(pharmfreq.GENE_ENZYMES.values()) - covered)
    if uncovered:
        report.warn(f"mapped to a PharmFreq gene but carrying no profile: "
                    f"{', '.join(uncovered)}")
    report.ok(f"{n} metabolizer-status quote(s) re-derived from the pinned export, "
              f"exact match")
    check_cpic_guidance(report, meta, drugs)
