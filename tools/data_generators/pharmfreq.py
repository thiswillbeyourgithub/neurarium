"""Read the committed PharmFreq metabolizer-status export (corpus #13).

The export itself lives in `tools/data/pharmfreq/`, committed verbatim, one TSV per
gene. That is the unusual part of this corpus and the whole reason this module exists:
every other corpus keeps its pages author-side, so its quote gate is skipped on a clone,
but PharmFreq's files are small and freely redistributable, so they ship with the repo
and the gate runs everywhere.

Three consumers, one reader, so the numbers cannot drift between them:

* `tools/fetch/fetch_pharmfreq.py` turns the TSVs into
  `tools/generated_cache/enzyme_variability.json`;
* `data_generators/provenance.py` verifies, at generation time, that each TSV still
  hashes to what that cache pinned;
* `tools/check_data.py` re-derives every emitted profile and quote straight from the
  TSVs and requires an exact match.

**Why the quote is checked by derivation rather than by a page.** Every other corpus
gates a quote by finding it verbatim in a document somebody else wrote. There is no such
document here: PharmFreq publishes a table, and the sentence a reader sees is one we
compose out of it. Writing that sentence to a page file and then looking for it there
would be circular, so the gate instead pins the raw table by hash and rebuilds the
sentence from it, which is the same guarantee reached the honest way.

Stdlib only. Built with the help of Claude Code.
"""
from __future__ import annotations

import hashlib
import os

from .drugs import METABOLIZER_GROUPS, METABOLIZER_PHENOTYPES

# Repo-relative, so it can be handed to `check_data.py` through `meta.source_corpora`
# without ever naming an absolute path.
EXPORT_DIR = "tools/data/pharmfreq"

# PharmFreq's subgroup strings -> our slugs. Spelled out rather than slugified on the
# fly so an upstream rename is a loud failure here instead of a silently new group the
# viewer has no label for.
GROUP_SLUGS = {
    "European": "european",
    "Sub-Saharan African": "sub_saharan_african",
    "Middle East & North Africa": "middle_east_north_africa",
    "Central/South Asian": "central_south_asian",
    "East Asian": "east_asian",
    "Oceanian": "oceanian",
    "North American": "north_american",
    "South American": "south_american",
}

# PharmFreq gene symbol -> our ENZYMES key. Only where the two name the *same* enzyme:
# UGT1A1 is deliberately absent because we model the glucuronidation family as one `ugt`
# node covering it plus four other isoforms, and hanging UGT1A1's frequencies off that
# would publish one isoform's genetics as another's.
GENE_ENZYMES = {
    "CYP2B6": "cyp2b6",
    "CYP2C9": "cyp2c9",
    "CYP2C19": "cyp2c19",
    "CYP2D6": "cyp2d6",
    "CYP3A5": "cyp3a5",
}


class ExportError(Exception):
    """The export on disk is not the one this code knows how to read."""


def sha256(path: str) -> str:
    """The hash the cache pins a source file by."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def export_files(directory: str) -> list[str]:
    """The export's TSVs, sorted, by bare file name."""
    return sorted(n for n in os.listdir(directory) if n.endswith(".txt"))


def read_export(directory: str) -> dict[str, dict[str, dict[str, float]]]:
    """``gene -> group slug -> phenotype -> frequency``, from the committed TSVs."""
    names = export_files(directory)
    if not names:
        raise ExportError(f"{directory}: no .txt export in there")
    out: dict[str, dict[str, dict[str, float]]] = {}
    for name in names:
        with open(os.path.join(directory, name), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        for line in lines[1:]:  # the header row names the four columns
            if not line.strip():
                continue
            try:
                group, gene, phenotype, freq = line.split("\t")
            except ValueError:
                raise ExportError(f"{name}: not four tab-separated columns: {line!r}")
            if phenotype not in METABOLIZER_PHENOTYPES:
                raise ExportError(f"{name}: unknown phenotype {phenotype!r} "
                                  f"(extend METABOLIZER_PHENOTYPES)")
            slug = GROUP_SLUGS.get(group)
            if not slug:
                raise ExportError(f"{name}: unknown subgroup {group!r} "
                                  f"(extend GROUP_SLUGS + METABOLIZER_GROUPS)")
            out.setdefault(gene, {}).setdefault(slug, {})[phenotype] = float(freq)
    return out


def ordered_profile(profile: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """The profile in the order the viewer shows it, dropping groups the gene misses."""
    return {slug: profile[slug] for slug in METABOLIZER_GROUPS if slug in profile}


def pct(f: float) -> str:
    """A frequency as the percentage the quote and the panel both show."""
    return f"{f * 100:.1f}%"


def quote_for(gene: str, profile: dict[str, dict[str, float]]) -> str:
    """The one verbatim line that carries the whole profile.

    One node per enzyme rather than one per population group (see CLAUDE.md, Expression
    density, for the same reasoning on Allen profiles), so the numbers a reader judges
    the claim by all have to live inside the quote.
    """
    parts = []
    for slug in METABOLIZER_GROUPS:
        row = profile.get(slug)
        if not row:
            continue
        got = ", ".join(f"{ph} {pct(row[ph])}"
                        for ph in METABOLIZER_PHENOTYPES if ph in row)
        parts.append(f"{METABOLIZER_GROUPS[slug]['en']} {got}")
    return (f"{gene} metabolizer phenotype frequencies by population group "
            f"(PharmFreq): " + "; ".join(parts))
