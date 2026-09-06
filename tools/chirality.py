#!/usr/bin/env python
"""Stereochemistry-aware ligand-name matching, shared by the affinity fetchers.

Both external affinity sources (PDSP `fetch/fetch_ki.py`, GtoPdb
`fetch/fetch_gtopdb_ki.py`) join their rows to our drugs **by ligand name**, and
both used a normalizer that threw away every non-alphanumeric character. That
silently equated a single enantiomer with the racemate: `(-)-pentazocine` and
`PENTAZOCINE (+)` both collapsed to `pentazocine`, so one molecule's assays were
published as another's. It is the exact failure `CLAUDE.local.md` forbids when it
says the armodafinil/modafinil and esketamine/ketamine near-misses are deliberately
NOT aliased: a borrowed assay presented as ours is a false `verified`.

It is not enough to reject every stereo-tagged row, because for several drugs the
tagged row IS the substance: natural nicotine is (-)-nicotine, LSD is (+)-LSD,
cocaine is (-)-cocaine. Which stereoisomer a drug id denotes is a fact about the
drug, so it is declared here in :data:`STEREO` rather than guessed from the row.

The rule, then:

* a row with **no** stereo tag matches its stem's drug, as before;
* a row tagged as a **racemate** (`(+-)`, `(+/-)`, `(±)`) matches only a drug we
  model as a racemate (no :data:`STEREO` entry);
* a row tagged with a **single enantiomer** matches only a drug that declares that
  same enantiomer.

Deliberately narrow: it reads the tag, never invents one. A drug whose PDSP entry
lives under a different name entirely (pethidine as `Meperidine`) is out of scope
here and stays with each fetcher's explicit alias map, which is exact-match and
already carries the "measured as <compound>" warning.

Stdlib only; authoring helper, not served.

Built with the help of Claude Code.
"""
from __future__ import annotations

import html
import re

# Which single stereoisomer a drug id denotes, for the drugs whose source rows
# carry a stereo tag. "+" / "-" are the optical-rotation labels the two databases
# use. A drug absent from this map is taken to be the racemate (or achiral), which
# is the common case and the safe default: it then accepts untagged and explicitly
# racemic rows, and refuses a single-enantiomer one.
STEREO = {
    # The natural / marketed substance IS the single enantiomer here, so its
    # tagged rows are the right ones and its antipode's must not pool in.
    "cocaine": "-",           # natural cocaine is (-)-cocaine
    "nicotine": "-",          # natural nicotine is (-)-nicotine
    "lsd": "+",               # LSD is (+)-LSD (d-lysergic acid diethylamide)
    "cytisine": "-",          # natural cytisine is (-)-cytisine
    "methamphetamine": "+",   # the modeled substance is (+)/d-methamphetamine
}

# A trailing or leading optical-rotation tag: "(-)-baclofen", "PENTAZOCINE (+)",
# "Tramadol,(+)", "Pentazocine,(+/-)", "(±)-nicotine". Only parenthesised tags are
# read, so an unrelated hyphen ("N-desmethylclozapine", "Methylphenidate-d") is
# left alone and keeps matching exactly as before.
_TAG = r"\(\s*(±|\+\s*/\s*-|\+-|-\s*/\s*\+|\+|-|−|–)\s*\)"
_LEAD = re.compile(r"^\s*" + _TAG + r"\s*[-‐-―]?\s*", re.I)
_TRAIL = re.compile(r"\s*[,\-‐-―]?\s*" + _TAG + r"\s*$", re.I)

_RACEMIC = {"±", "+/-", "+-", "-/+"}


def plain(s: str) -> str:
    """Strip markup + entities from a source's ligand name (GtoPdb ships HTML)."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def split_stereo(name: str):
    """Return (stem, tag) for a ligand name.

    `tag` is None when the name carries no optical-rotation marker, "+-" when it
    is explicitly racemic, else "+" or "-". `stem` is the name with that marker
    removed (still raw: normalize it however the caller normalizes drug names).
    """
    s = plain(name)
    tag = None
    for rx in (_LEAD, _TRAIL):
        m = rx.search(s)
        if m:
            raw = re.sub(r"\s+", "", m.group(1))
            tag = "+-" if raw in _RACEMIC else ("-" if raw in {"-", "−", "–"} else "+")
            s = (s[:m.start()] + s[m.end():]).strip(" ,-")
            break
    return s, tag


def tag_allowed(tag, drug_id) -> bool:
    """Whether a row carrying `tag` may be counted as `drug_id`'s own measurement."""
    if tag is None:
        return True
    want = STEREO.get(drug_id)
    if want is None:                 # we model the racemate: only racemic rows join
        return tag == "+-"
    return tag == want               # we model one enantiomer: only that one joins
